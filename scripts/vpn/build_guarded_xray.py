#!/usr/bin/python3
"""Reproducible opt-in CRM source-IP admission patch for the pinned upstream Xray release.

Build on Linux: python3 build_guarded_xray.py /path/to/Xray-core
The checkout must be v26.9.9. The ordinary binary is backed up before deployment.
"""
import subprocess
import os
import sys
from pathlib import Path


def patch(checkout):
    checkout = Path(checkout)
    version = subprocess.check_output(['git', '-C', str(checkout), 'describe', '--tags', '--exact-match'], text=True).strip()
    if version != 'v26.9.9':
        raise RuntimeError('unsupported_xray_version')
    target = checkout / 'app/dispatcher/default.go'
    source = target.read_text()
    if 'crmGuardContext(ctx)' not in source:
        marker = 'func (d *DefaultDispatcher) Dispatch(ctx context.Context, destination net.Destination) (*transport.Link, error) {'
        source = source.replace(marker, marker + '\n\tvar err error\n\tctx, err = crmGuardContext(ctx)\n\tif err != nil { return nil, err }', 1)
        marker = 'func (d *DefaultDispatcher) DispatchLink(ctx context.Context, destination net.Destination, outbound *transport.Link) error {'
        source = source.replace(marker, marker + '\n\tvar err error\n\tctx, err = crmGuardContext(ctx)\n\tif err != nil { common.Interrupt(outbound.Reader); common.Interrupt(outbound.Writer); return err }', 1)
        marker = '\tinbound, outbound := d.getLink(ctx)'
        source = source.replace(marker, marker + '\n\tcontext.AfterFunc(ctx, func() { common.Interrupt(inbound.Reader); common.Interrupt(inbound.Writer); common.Interrupt(outbound.Reader); common.Interrupt(outbound.Writer) })', 1)
        marker = '\toutbound = WrapLink(ctx, d.policy, d.stats, outbound)'
        source = source.replace(marker, '\tcontext.AfterFunc(ctx, func() { common.Interrupt(outbound.Reader); common.Interrupt(outbound.Writer) })\n' + marker, 1)
        if source.count('crmGuardContext(ctx)') != 2:
            raise RuntimeError('patch_target_changed')
        target.write_text(source)
    (checkout / 'app/dispatcher/crm_guard.go').write_text(Path(__file__).with_name('xray_crm_guard.go').read_text())
    (checkout / 'app/dispatcher/crm_guard_test.go').write_text(Path(__file__).with_name('xray_crm_guard_test.go').read_text())
    subprocess.run(['gofmt', '-w', 'app/dispatcher/crm_guard.go', 'app/dispatcher/default.go'], cwd=checkout, check=True)
    subprocess.run(['go', 'test', '-race', './app/dispatcher', '-run', '^TestCRMGuard$', '-count=1'], cwd=checkout, check=True, env={**os.environ, 'CGO_ENABLED': '1'})
    subprocess.run(['go', 'build', '-trimpath', '-ldflags=-s -w', '-o', '/opt/crm-vpn/xray-crm', './main'], cwd=checkout, check=True, env={**os.environ, 'CGO_ENABLED': '0'})


if __name__ == '__main__':
    patch(sys.argv[1])
