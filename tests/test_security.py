from unittest.mock import patch

import pytest
import requests

import security
from conftest import make_response


@pytest.mark.parametrize(
    "address,expected",
    [
        ("93.184.216.34", True),
        ("8.8.8.8", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("172.16.3.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),  # metadata de nuvem
        ("0.0.0.0", False),
        ("::1", False),
        ("fe80::1", False),
        ("::ffff:127.0.0.1", False),  # IPv4 mapeado em IPv6
        ("224.0.0.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public_ip(address, expected):
    assert security.is_public_ip(address) is expected


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "http://127.0.0.1:8080/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "https://user:pass@example.com/",
        "http:///nohost",
    ],
)
def test_assert_public_url_rejects_dangerous_targets(url):
    with pytest.raises(security.UnsafeURLError):
        security.assert_public_url(url)


def test_hostname_resolving_to_private_ip_is_rejected(monkeypatch):
    monkeypatch.setattr(security, "_resolve_host", lambda host: ["10.1.2.3"])
    with pytest.raises(security.UnsafeURLError):
        security.assert_public_url("https://internal.example.com/")


def test_any_private_address_among_many_blocks(monkeypatch):
    monkeypatch.setattr(security, "_resolve_host", lambda host: ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(security.UnsafeURLError):
        security.assert_public_url("https://rebind.example.com/")


@patch("security.requests.get")
def test_safe_get_returns_body_and_disables_auto_redirects(mock_get):
    mock_get.return_value = make_response(b"<html>ok</html>")
    response = security.safe_get("https://example.com/a")
    assert response.content == b"<html>ok</html>"
    assert mock_get.call_args.kwargs["allow_redirects"] is False


@patch("security.requests.get")
def test_safe_get_revalidates_every_redirect_hop(mock_get):
    mock_get.side_effect = [
        make_response(b"", 302, {"Location": "http://169.254.169.254/latest/"}),
    ]
    with pytest.raises(security.UnsafeURLError):
        security.safe_get("https://example.com/redirect")
    assert mock_get.call_count == 1  # o destino interno nunca foi requisitado


@patch("security.requests.get")
def test_safe_get_follows_relative_redirects(mock_get):
    mock_get.side_effect = [
        make_response(b"", 301, {"Location": "/final"}),
        make_response(b"done"),
    ]
    assert security.safe_get("https://example.com/start").content == b"done"
    assert mock_get.call_args.args[0] == "https://example.com/final"


@patch("security.requests.get")
def test_safe_get_limits_redirect_chain(mock_get):
    mock_get.side_effect = lambda *a, **k: make_response(b"", 302, {"Location": "https://example.com/loop"})
    with pytest.raises(requests.TooManyRedirects):
        security.safe_get("https://example.com/loop", max_redirects=3)


@patch("security.requests.get")
def test_safe_get_rejects_oversized_body(mock_get):
    mock_get.return_value = make_response(b"x" * 2048)
    with pytest.raises(security.ResponseTooLargeError):
        security.safe_get("https://example.com/big", max_bytes=1024)


@patch("security.requests.get")
def test_safe_get_rejects_oversized_declared_length(mock_get):
    mock_get.return_value = make_response(b"x", headers={"Content-Length": "999999999"})
    with pytest.raises(security.ResponseTooLargeError):
        security.safe_get("https://example.com/big", max_bytes=1024)
