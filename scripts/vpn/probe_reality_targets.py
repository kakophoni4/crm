#!/usr/bin/python3
"""Read-only TLS target survey from the VPN nodes, with no client credentials.

TLS timings include DNS/connect/handshake and are not a customer's VPN latency.
Run on CRM, which owns the private node inventory and pinned SSH configuration.
"""
import argparse
import concurrent.futures
import json
import subprocess
from pathlib import Path


TARGETS = {
    'Steam': ['store.steampowered.com', 'steamcommunity.com', 'cdn.akamai.steamstatic.com',
              'cdn.cloudflare.steamstatic.com', 'cdn.fastly.steamstatic.com',
              'shared.fastly.steamstatic.com', 'shared.akamai.steamstatic.com'],
    'Riot': ['www.riotgames.com', 'auth.riotgames.com', 'l3cdn.riotgames.com',
             'status.riotgames.com', 'playvalorant.com', 'www.leagueoflegends.com'],
    'Roblox': ['setup.rbxcdn.com', 'www.roblox.com', 'www.rbxcdn.com'],
    'Epic Games': ['www.epicgames.com', 'store.epicgames.com', 'download.epicgames.com',
                   'cdn1.unrealengine.com', 'static-assets-prod.epicgames.com',
                   'fastly-download.epicgames.com'],
    'Battle.net': ['www.blizzard.com', 'www.battle.net', 'account.battle.net'],
    'EA': ['www.ea.com', 'help.ea.com', 'accounts.ea.com'],
    'Ubisoft': ['www.ubisoft.com', 'staticctf.ubisoft.com', 'account.ubisoft.com'],
    'Xbox': ['www.xbox.com', 'assets.xboxservices.com'],
    'PlayStation': ['www.playstation.com', 'store.playstation.com'],
    'Nintendo': ['www.nintendo.com', 'accounts.nintendo.com'],
    'GOG': ['www.gog.com', 'images.gog-statics.com'],
    'Rockstar Games': ['www.rockstargames.com', 'socialclub.rockstargames.com'],
    'Wargaming': ['worldoftanks.eu', 'worldofwarships.eu'],
    'Minecraft': ['www.minecraft.net', 'piston-meta.mojang.com', 'piston-data.mojang.com'],
    'Discord': ['discord.com', 'cdn.discordapp.com'],
    'Twitch': ['www.twitch.tv', 'static.twitchcdn.net'],
    'Bungie': ['www.bungie.net'],
    'Warframe': ['www.warframe.com'],
    'Path of Exile': ['www.pathofexile.com'],
    'Final Fantasy XIV': ['www.finalfantasyxiv.com'],
}

NODE_SCRIPT = r'''
import concurrent.futures,json,socket,ssl,time
def check(item):
 brand,host=item;started=time.monotonic()
 try:
  context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_3
  context.set_alpn_protocols(['h2'])
  with socket.create_connection((host,443),timeout=5) as raw:
   with context.wrap_socket(raw,server_hostname=host) as stream:
    return {'brand':brand,'host':host,'valid':stream.version()=='TLSv1.3' and stream.selected_alpn_protocol()=='h2',
            'tls':stream.version(),'alpn':stream.selected_alpn_protocol(),'ms':round((time.monotonic()-started)*1000)}
 except Exception as error:
  return {'brand':brand,'host':host,'valid':False,'error':type(error).__name__}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for item in pool.map(check,TARGETS):print(json.dumps(item),flush=True)
'''


def check_node(node, targets):
    source = 'TARGETS=' + repr(targets) + '\n' + NODE_SCRIPT
    result = subprocess.run(['ssh', '-F', '/etc/crm-vpn/ssh_config', 'vpn-' + node['id'], 'python3', '-'],
                            input=source, text=True, capture_output=True, timeout=150)
    if result.returncode:
        return {'node': node['id'], 'error': 'target_survey_failed'}
    try:
        return {'node': node['id'], 'targets': [json.loads(line) for line in result.stdout.splitlines()]}
    except ValueError:
        return {'node': node['id'], 'error': 'invalid_survey_response'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--node')
    parser.add_argument('--brand', action='append', choices=list(TARGETS))
    args = parser.parse_args()
    nodes = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())['nodes']
    if args.node:
        nodes = [node for node in nodes if node['id'] == args.node]
        if not nodes:
            raise SystemExit('Unknown inventory node')
    targets = [(brand, host) for brand, hosts in TARGETS.items()
               if not args.brand or brand in args.brand for host in hosts]
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        for result in pool.map(lambda node: check_node(node, targets), nodes):
            print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
