"""Local fixture helpers and a network tripwire for every Phase 2B parser test."""

import socket
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Parser tests must not use the network")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def fixture_text():
    root = Path(__file__).resolve().parents[1] / "fixtures"

    def read(source, filename):
        return (root / source / filename).read_text(encoding="utf-8")

    return read


@pytest.fixture
def html_response():
    def make(html, url="https://example.test/p/index.html", meta=None):
        return HtmlResponse(
            url,
            body=html.encode("utf-8"),
            encoding="utf-8",
            request=Request(url, meta=meta or {}),
        )

    return make
