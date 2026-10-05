"""Refresh public routing databases atomically after release SHA256 verification."""
import hashlib
import urllib.request
from pathlib import Path

ROOT = Path('/opt/crm-vpn/geo')
BASE = 'https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    for name in ('geoip', 'geosite'):
        with urllib.request.urlopen(BASE + name + '.dat', timeout=60) as response:
            data = response.read(50 * 1024 * 1024)
        with urllib.request.urlopen(BASE + name + '.dat.sha256sum', timeout=30) as response:
            expected = response.read(1024).decode().split()[0]
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('Geodata checksum mismatch; existing database retained')
        temporary = ROOT / (name + '.dat.new')
        temporary.write_bytes(data); temporary.chmod(0o644)
        temporary.replace(ROOT / (name + '.dat'))
        print(name + ' verified and updated')


if __name__ == '__main__':
    main()
