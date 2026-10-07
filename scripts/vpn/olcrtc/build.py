"""Build the CRM room supervisor inside a pinned, separately checked out olcRTC module."""
import argparse
import shutil
import subprocess
from pathlib import Path

UPSTREAM_COMMIT = '403edd409011dd371796260196ecd17630df0fdd'
parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('--go', default='go')
parser.add_argument('--output', required=True)
args = parser.parse_args()
revision = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
if revision != UPSTREAM_COMMIT:
    raise SystemExit('The olcRTC checkout must match the audited upstream commit')
subprocess.run(['git', '-C', str(args.source), 'diff', '--quiet', 'HEAD', '--', '.', ':!cmd/crm-vpn'], check=True)
target = args.source / 'cmd' / 'crm-vpn'
target.mkdir(parents=True, exist_ok=True)
for name in ('main.go', 'main_test.go'):
    source = Path(__file__).with_name(name)
    if source.exists():
        shutil.copyfile(source, target / name)
subprocess.run([args.go, 'test', './cmd/crm-vpn'], cwd=args.source, check=True)
import os
environment = {**os.environ, 'CGO_ENABLED': '0', 'GOOS': 'linux', 'GOARCH': 'amd64'}
subprocess.run([args.go, 'build', '-trimpath', '-o', args.output, './cmd/crm-vpn'],
               cwd=args.source, env=environment, check=True)
