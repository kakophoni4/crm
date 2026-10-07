# Ghostlane / olcRTC

The Ghostlane subscription (`?format=ghostlane`) combines the existing VLESS and
Hysteria2 links with one personal Jitsi Datachannel room. Happ and Clash output
remain unchanged: they do not support olcRTC.

Rooms are allocated lazily when the Ghostlane subscription is first fetched.
The control plane selects a healthy VPN node, preferring fewer assigned active
rooms, with the existing node load ranking as the tie breaker. Assignment remains
stable. Each subscription gets its own unpredictable room and derived encryption
key. The CRM host provisions and collects counters; VPN payload exits the assigned
VPN VPS. A Jitsi relay is an additional network hop, so latency depends on it too.

## Build and installation

Use a separate checkout of `https://github.com/ghostlane-project/olcrtc` at
`403edd409011dd371796260196ecd17630df0fdd`, with Go 1.26.3 or newer:

```console
python scripts/vpn/olcrtc/build.py /path/to/olcrtc --output /path/to/crm-vpn-olcrtc
```

The build runs the admission tests before producing a Linux amd64 binary. The
original source must be unchanged. `UPSTREAM_LICENSE` and `UPSTREAM_NOTICE`
accompany the resulting binary.

Place the binary and `install_olcrtc.py`, `node_agent.py`, `olcrtc_node.py` in
`/opt/crm-vpn` on CRM. Run `python3 /opt/crm-vpn/install_olcrtc.py`. It uses the
private existing SSH inventory, verifies the binary checksum, and backs up the
old agent before installing. A node failure rolls back the agent and stops the
new RTC service. Existing Xray and Hysteria binaries and transport settings are
not changed.

Deploy `olcrtc_control.py` alongside `control_service.py` and set
`VPN_OLCRTC_JITSI_BASE` in the private control environment to the chosen HTTPS
Jitsi instance, then restart `crm-vpn-control`. Without this setting allocation
and synchronization are disabled. Do not commit the inventory, environment,
room files, subscription URLs, or built binaries.

The node service runs as `crm-vpn-rtc`, with a 512 MB memory ceiling. Its room
file is `/var/lib/crm-vpn-rtc/rooms.json`, root-owned and group-readable only.
Stats listeners bind to loopback. `AF_NETLINK` is needed for WebRTC interface
discovery. One supervisor process hosts the node's rooms; there is no process per
room. Inspect systemd state and loopback statistics to diagnose a failure.

## Limits, expiry and accounting

The room key is validated by the upstream encrypted handshake. The custom
authorization hook acquires a central lease before accepting a client, renews it
every ten seconds, and releases it on disconnect. Authorization checks local
subscription expiry and enabled state as well. Central failure denies new
clients and closes established sessions when renewal fails. Abandoned leases
expire after 45 seconds. Revocation or expiry removes the room on synchronization.

The same ledger applies the subscription's CRM limit of 3 by default, at most 8,
across direct VPN and RTC. A relay cannot reveal the client's external IP;
olcRTC therefore counts its stable client device ID as a separate slot. Direct
protocols retain the existing external-IP policy. A device using both kinds of
tunnel can occupy two slots. Synthetic slot addresses never appear in CRM views;
only the count and limit do. Jitsi provider capacity is separate from this policy.

Per-room byte counters are added to the existing traffic totals. Publishing a
room link requires a recent successful node status poll. This confirms server
readiness, not reachability from every mobile operator. Validate a connection
from the affected mobile network before claiming that a restriction is bypassed.
