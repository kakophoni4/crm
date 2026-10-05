#!/usr/bin/python3
"""Consistent local control-plane backup. Run as root; archives contain private keys."""
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path


def main():
    backup = Path('/var/backups/crm-vpn')
    backup.mkdir(parents=True, exist_ok=True); backup.chmod(0o700)
    archive = backup / (time.strftime('%Y-%m-%d-%H%M%S', time.gmtime()) + '.tar.gz')
    with tempfile.TemporaryDirectory(prefix='crm-vpn-backup-', dir=backup) as name:
        stage = Path(name)
        source = sqlite3.connect('file:/var/lib/crm-vpn-control/control.sqlite?mode=ro', uri=True)
        destination = sqlite3.connect(stage / 'control.sqlite')
        try:
            source.backup(destination)
        finally:
            source.close(); destination.close()
        files = {
            'bot.env': '/etc/crm-vpn/bot.env', 'control.env': '/etc/crm-vpn/control.env',
            'crm.env': '/etc/crm-vpn/crm.env', 'nodes.json': '/etc/crm-vpn/nodes.json',
            'control-ssh': '/var/lib/crm-vpn-control/.ssh',
        }
        for label, original in files.items():
            path = Path(original)
            if path.is_dir(): shutil.copytree(path, stage / label)
            else: shutil.copy2(path, stage / label)
        with tarfile.open(archive, 'w:gz') as tar:
            for path in stage.iterdir(): tar.add(path, arcname=path.name)
    archive.chmod(0o600)
    for path in backup.glob('*.tar.gz'):
        if path.stat().st_mtime < time.time() - 14 * 86400: path.unlink()
    print('VPN control database and credentials backed up')


if __name__ == '__main__': main()
