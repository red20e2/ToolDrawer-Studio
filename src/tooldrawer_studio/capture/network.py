from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable


_RFC1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def is_private_lan_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if address.version != 4:
        return False
    return any(address in network for network in _RFC1918_NETWORKS)


def private_ipv4_candidates() -> tuple[str, ...]:
    try:
        discovered = socket.getaddrinfo(
            socket.gethostname(),
            None,
            family=socket.AF_INET,
        )
    except socket.gaierror:
        return ()

    result: list[str] = []
    seen: set[str] = set()
    for entry in discovered:
        address = entry[4][0]
        if address in seen or not is_private_lan_ipv4(address):
            continue
        seen.add(address)
        result.append(address)
    return tuple(result)


def select_private_ipv4(candidates: Iterable[str]) -> str:
    for candidate in candidates:
        if is_private_lan_ipv4(candidate):
            return candidate
    raise RuntimeError("No private/local IPv4 address is available for phone capture")
