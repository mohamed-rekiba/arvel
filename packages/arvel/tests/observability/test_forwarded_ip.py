"""Trusted-proxy aware client-IP resolution."""

from __future__ import annotations

from arvel.observability.forwarded import ip_in_cidrs, resolve_client_ip


def test_no_trusted_proxies_ignores_forwarded_header() -> None:
    ip = resolve_client_ip(
        peer_ip="203.0.113.5",
        forwarded_for="10.0.0.1",
        trusted_proxies=[],
    )
    assert ip == "203.0.113.5"


def test_untrusted_peer_ignores_forwarded_header() -> None:
    ip = resolve_client_ip(
        peer_ip="203.0.113.5",
        forwarded_for="10.0.0.1",
        trusted_proxies=["192.168.0.0/16"],
    )
    assert ip == "203.0.113.5"


def test_trusted_peer_returns_rightmost_untrusted_hop() -> None:
    ip = resolve_client_ip(
        peer_ip="192.168.1.1",
        forwarded_for="9.9.9.9, 192.168.1.2",
        trusted_proxies=["192.168.0.0/16"],
    )
    assert ip == "9.9.9.9"


def test_trusted_peer_all_hops_trusted_falls_back_to_peer() -> None:
    ip = resolve_client_ip(
        peer_ip="192.168.1.1",
        forwarded_for="192.168.1.2, 192.168.1.3",
        trusted_proxies=["192.168.0.0/16"],
    )
    assert ip == "192.168.1.1"


def test_ip_in_cidrs_skips_malformed_entries() -> None:
    assert ip_in_cidrs("203.0.113.9", ["nonsense", "203.0.113.0/24"]) is True
    assert ip_in_cidrs("8.8.8.8", ["nonsense"]) is False
    assert ip_in_cidrs("not-an-ip", ["0.0.0.0/0"]) is False
