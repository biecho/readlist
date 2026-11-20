from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from readlist.http import HttpError

PDF = b"%PDF-1.7\n" + b"x" * 20_000


class FakeHttp:
    """Serves canned responses by URL prefix; anything else is a 404."""

    def __init__(self, routes: dict[str, bytes | int] | None = None):
        self.routes = dict(routes or {})
        self.requests: list[str] = []

    def get(self, url, headers=None):
        self.requests.append(url)
        for prefix, response in self.routes.items():
            if url.startswith(prefix):
                if isinstance(response, int):
                    raise HttpError(url, response)
                return response
        raise HttpError(url, 404)

    def get_json(self, url, headers=None):
        return json.loads(self.get(url, headers))

    def get_xml(self, url):
        return ET.fromstring(self.get(url))


def arxiv_feed(*entries: tuple[str, str]) -> bytes:
    items = "".join(
        f"<entry><id>http://arxiv.org/abs/{i}v1</id><title>{t}</title></entry>" for i, t in entries)
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{items}</feed>'.encode()


@pytest.fixture
def fake_http():
    return FakeHttp()
