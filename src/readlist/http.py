"""A polite HTTP client: identifies itself, spaces out requests per host, backs off on 429."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

from readlist import __version__

USER_AGENT = f"readlist/{__version__} (+https://github.com/biecho/readlist)"
DEFAULT_INTERVAL_SECONDS = 1.0
# arXiv asks automated clients to wait 3 seconds between requests.
HOST_INTERVAL_SECONDS = {"export.arxiv.org": 3.0, "arxiv.org": 3.0}
RETRY_STATUSES = {429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, url: str, status: int | None, reason: str = ""):
        self.url = url
        self.status = status
        super().__init__(f"{url}: {status or ''} {reason}".strip())


class Fetcher(Protocol):
    """What resolvers and commands need. Tests substitute a fake."""

    def get(self, url: str, headers: dict[str, str] | None = None) -> bytes: ...
    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any: ...
    def get_xml(self, url: str) -> ET.Element: ...


class Http:
    def __init__(
        self,
        *,
        retries: int = 3,
        timeout: float = 60,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.retries = retries
        self.timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}

    def get(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        for attempt in range(self.retries + 1):
            self._wait_turn(url)
            try:
                return self._request(url, headers or {})
            except urllib.error.HTTPError as problem:
                if problem.code in RETRY_STATUSES and attempt < self.retries:
                    self._sleep(_backoff(problem, attempt))
                    continue
                raise HttpError(url, problem.code, problem.reason) from problem
            except (urllib.error.URLError, TimeoutError, OSError) as problem:
                if attempt < self.retries:
                    self._sleep(2 ** attempt)
                    continue
                raise HttpError(url, None, str(problem)) from problem
        raise AssertionError("unreachable: the loop returns or raises")

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        return json.loads(self.get(url, headers))

    def get_xml(self, url: str) -> ET.Element:
        return ET.fromstring(self.get(url))

    def _wait_turn(self, url: str) -> None:
        host = urlsplit(url).netloc
        interval = HOST_INTERVAL_SECONDS.get(host, DEFAULT_INTERVAL_SECONDS)
        last = self._last_request.get(host)
        if last is not None:
            remaining = interval - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _request(self, url: str, headers: dict[str, str]) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()


def _backoff(problem: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = problem.headers.get("Retry-After") if problem.headers else None
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 60.0)
    return 2.0 * 2 ** attempt
