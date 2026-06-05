from __future__ import annotations

import ipaddress
from typing import Any


def ip_allowed(client_ip: str, allowlist: list[Any] | None) -> bool:
    if not allowlist:
        return True
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowlist:
        network = ipaddress.ip_network(str(entry), strict=False)
        if addr in network:
            return True
    return False
