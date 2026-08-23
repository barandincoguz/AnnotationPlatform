from ipaddress import ip_network

from starlette.requests import Request

from backend import config
from backend.users.deps import get_request_ip


def _request(peer: str, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (peer, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def _configure(monkeypatch, *, trusted: bool, networks=()):
    monkeypatch.setattr(config, "TRUST_FORWARDED_FOR", trusted)
    monkeypatch.setattr(config, "TRUSTED_PROXY_NETWORKS", networks)
    monkeypatch.setattr(config, "SPACE_ID", None, raising=False)


def test_forwarded_for_ignored_when_trust_disabled(monkeypatch):
    _configure(monkeypatch, trusted=False)
    request = _request("203.0.113.10", "198.51.100.7")
    assert get_request_ip(request) == "203.0.113.10"


def test_forwarded_for_ignored_from_untrusted_peer(monkeypatch):
    _configure(
        monkeypatch,
        trusted=True,
        networks=(ip_network("10.0.0.0/8"),),
    )
    request = _request("203.0.113.10", "198.51.100.7")
    assert get_request_ip(request) == "203.0.113.10"


def test_space_id_does_not_override_explicit_proxy_trust(monkeypatch):
    _configure(monkeypatch, trusted=False)
    monkeypatch.setattr(config, "SPACE_ID", "owner/space")
    request = _request("203.0.113.10", "198.51.100.7")
    assert get_request_ip(request) == "203.0.113.10"


def test_nearest_untrusted_address_selected(monkeypatch):
    _configure(
        monkeypatch,
        trusted=True,
        networks=(ip_network("10.0.0.0/8"),),
    )
    request = _request(
        "10.0.0.2",
        "192.0.2.99, 198.51.100.7, 10.0.0.3",
    )
    assert get_request_ip(request) == "198.51.100.7"


def test_invalid_forwarded_values_do_not_become_rate_limit_keys(monkeypatch):
    _configure(
        monkeypatch,
        trusted=True,
        networks=(ip_network("10.0.0.0/8"),),
    )
    request = _request("10.0.0.2", "garbage, also-not-an-ip")
    assert get_request_ip(request) == "10.0.0.2"


def test_ipv6_forwarded_address_is_canonicalized(monkeypatch):
    _configure(
        monkeypatch,
        trusted=True,
        networks=(ip_network("fd00::/8"),),
    )
    request = _request("fd00::2", "2001:0db8:0:0:0:0:0:1")
    assert get_request_ip(request) == "2001:db8::1"
