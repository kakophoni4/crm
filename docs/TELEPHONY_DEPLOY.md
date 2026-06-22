# Telephony Deploy

The current VPS uses `matrix-caddy` as the public TLS proxy. CRM containers are
published on localhost-like host ports:

- API: `127.0.0.1:19001`
- Frontend: `127.0.0.1:19090`
- Caddyfile: `/opt/matrix/data/caddy/Caddyfile`

## DNS

Create an `A` record:

```text
pbx.bttsrvvrs.org -> 146.19.125.32
```

## Deploy Asterisk

From `/root/crm` on the server:

```bash
git pull
bash scripts/deploy/vps/update.sh
bash scripts/deploy/vps/telephony-up.sh
PBX_DOMAIN=pbx.bttsrvvrs.org bash scripts/deploy/vps/install-telephony-caddy.sh
```

Open firewall/security-group UDP ports `12000-12100` for RTP media. Port `18088`
must stay local-only; Caddy exposes it as `wss://pbx.bttsrvvrs.org/ws`.

## CRM Setting

In the CRM telephony account set:

```text
WebRTC WS URL = wss://pbx.bttsrvvrs.org/ws
PBX extension prefix = 71
```

## What Is Still Manual

The checked-in Asterisk config is safe by default: outbound calls return `501`.
After `telephony-sync.sh` runs, active CRM telephony accounts become Bitcall
trunks and active CRM telephony extensions become WebRTC SIP users in generated
include files:

- `deploy/server/asterisk/pjsip.generated.conf`
- `deploy/server/asterisk/extensions.generated.conf`

The `crm-telephony-sync` sidecar keeps these files updated automatically, so new
operator extensions are picked up by Asterisk within about 5 seconds.

Do not commit generated Bitcall provider passwords to git.

## Normal Operator Flow

1. Admin creates/updates a Bitcall account in CRM.
2. Operator opens the Telephony page and clicks Connect once. CRM creates that
   operator's internal WebRTC extension.
3. The sync sidecar renders the extension into Asterisk and reloads it.
4. The frontend waits briefly on first connect, then registers the browser SIP
   client.
