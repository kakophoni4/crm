#!/usr/bin/python3
"""Publish unmodified stable APKs from the original developers; verify GitHub digests."""
import concurrent.futures
import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

TARGET = Path(os.environ.get('VPN_DOWNLOADS_DIR', '/opt/crm-vpn/downloads'))
SOURCES = [
    ('ghostlane', 'ghostlane-project/ghostlane', lambda name: name.startswith('Ghostlane-') and name.endswith('-android-release.apk'), 'ghostlane.apk'),
    ('happ', 'Happ-proxy/happ-android', lambda name: name == 'Happ.apk', 'happ.apk'),
    ('clashmeta', 'MetaCubeX/ClashMetaForAndroid', lambda name: name.endswith('-meta-universal-release.apk'), 'clashmeta.apk'),
    ('v2rayng', '2dust/v2rayNG', lambda name: name.endswith('_arm64-v8a.apk') and '-fdroid' not in name, 'v2rayng.apk'),
    ('v2rayng-arm7', '2dust/v2rayNG', lambda name: name.endswith('_armeabi-v7a.apk') and '-fdroid' not in name, 'v2rayng-arm7.apk'),
]


def fetch(source):
    key, repo, select, filename = source
    request = urllib.request.Request('https://api.github.com/repos/' + repo + '/releases/latest', headers={'User-Agent': 'BTT-VPN-client-downloads', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    if release.get('prerelease') or release.get('draft'):
        raise ValueError('Expected a stable release: ' + repo)
    assets = [asset for asset in release['assets'] if select(asset['name'])]
    if len(assets) != 1:
        raise ValueError('APK asset is ambiguous: ' + repo)
    asset = assets[0]
    digest = asset.get('digest', '')
    if not digest or not digest.startswith('sha256:'):
        raise ValueError('Missing official SHA256: ' + repo)
    url = asset['browser_download_url']
    if not url.startswith('https://github.com/' + repo + '/releases/download/'):
        raise ValueError('Unexpected asset origin')
    destination = TARGET / filename
    temporary = TARGET / (filename + '.tmp')
    checksum = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'BTT-VPN-client-downloads'}), timeout=120) as response, temporary.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 400 * 1024**2:
                raise ValueError('APK exceeds expected size')
            checksum.update(chunk)
            output.write(chunk)
    if checksum.hexdigest() != digest.removeprefix('sha256:') or size != asset['size']:
        temporary.unlink(missing_ok=True)
        raise ValueError('APK integrity mismatch: ' + key)
    with zipfile.ZipFile(temporary) as apk:
        if 'AndroidManifest.xml' not in apk.namelist():
            raise ValueError('Not an Android application')
    temporary.chmod(0o644)
    temporary.replace(destination)
    print(key + ': official APK verified (' + release['tag_name'] + ')', flush=True)
    return key, {'version': release['tag_name'], 'sha256': checksum.hexdigest(), 'size': size, 'source': url, 'file': filename}


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    TARGET.chmod(0o755)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        result = dict(pool.map(fetch, SOURCES))
    path = TARGET / 'manifest.json.tmp'
    path.write_text(json.dumps(result, indent=2))
    path.chmod(0o644)
    path.replace(TARGET / 'manifest.json')


if __name__ == '__main__':
    main()
