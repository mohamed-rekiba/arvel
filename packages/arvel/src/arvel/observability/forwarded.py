"""Trusted-proxy aware client-IP resolution for CIDR-guarded infra endpoints.

``X-Forwarded-For`` is client-controlled. Honoring it for an access-control
decision lets anyone spoof an allowlisted IP, so we only trust it when the TCP
peer is itself a configured trusted proxy — the same stance as the reverb server.
"""

from __future__ import annotations

import ipaddress


def ip_in_cidrs(ip: str, cidrs: list[str]) -> bool:
    """True when ``ip`` falls in any CIDR (bad entries are skipped, not fatal)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def resolve_client_ip(
    *,
    peer_ip: str,
    forwarded_for: str | None,
    trusted_proxies: list[str],
) -> str:
    """Real client IP, honoring ``X-Forwarded-For`` only behind a trusted proxy.

    Without ``trusted_proxies`` configured the header is ignored — the peer is the
    client. When the peer is trusted, walk XFF right-to-left and return the first
    hop that isn't itself a trusted proxy.
    """
    if not trusted_proxies or not forwarded_for or not ip_in_cidrs(peer_ip, trusted_proxies):
        return peer_ip
    for hop in reversed([h.strip() for h in forwarded_for.split(",") if h.strip()]):
        if not ip_in_cidrs(hop, trusted_proxies):
            return hop
    return peer_ip


__all__ = ["ip_in_cidrs", "resolve_client_ip"]
