from __future__ import annotations

import importlib

import pytest


def _network_module():
    return importlib.import_module("tooldrawer_studio.capture.network")


def test_private_lan_ipv4_accepts_only_rfc1918_ranges():
    network = _network_module()

    assert network.is_private_lan_ipv4("10.25.1.8") is True
    assert network.is_private_lan_ipv4("172.16.0.1") is True
    assert network.is_private_lan_ipv4("172.31.255.254") is True
    assert network.is_private_lan_ipv4("192.168.4.20") is True

    assert network.is_private_lan_ipv4("127.0.0.1") is False
    assert network.is_private_lan_ipv4("169.254.4.2") is False
    assert network.is_private_lan_ipv4("172.32.0.1") is False
    assert network.is_private_lan_ipv4("8.8.8.8") is False
    assert network.is_private_lan_ipv4("0.0.0.0") is False


def test_select_private_ipv4_ignores_non_lan_addresses_and_preserves_order():
    network = _network_module()

    selected = network.select_private_ipv4(
        ["127.0.0.1", "8.8.8.8", "192.168.1.20", "10.0.0.40"]
    )

    assert selected == "192.168.1.20"


def test_select_private_ipv4_fails_closed_when_no_rfc1918_address_exists():
    network = _network_module()

    with pytest.raises(RuntimeError, match="private/local IPv4"):
        network.select_private_ipv4(["127.0.0.1", "169.254.1.2", "8.8.8.8"])


def test_private_ipv4_candidates_deduplicate_discovered_addresses(monkeypatch):
    network = _network_module()

    monkeypatch.setattr(
        network.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (network.socket.AF_INET, 1, 6, "", ("192.168.5.9", 0)),
            (network.socket.AF_INET, 1, 6, "", ("192.168.5.9", 0)),
            (network.socket.AF_INET, 1, 6, "", ("10.0.0.20", 0)),
        ],
    )

    assert network.private_ipv4_candidates() == ("192.168.5.9", "10.0.0.20")
