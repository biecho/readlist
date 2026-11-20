"""Download PDFs through a visible browser, for sites that refuse scripts.

Some publishers (ACM, behind Cloudflare) answer scripts with 403 and headless
browsers with a bot check, but serve the same open-access PDF to a person in
a browser. `readlist fetch --browser` drives the browser-use CLI
(https://github.com/browser-use/browser-use) in a visible window: it loads the
PDF, then fetches it from inside the page so the request carries the
browser's session.

The browser uses a fresh profile with none of your logins, so it gets only
what the site gives any visitor. If a check needs a click, click it in the
window; readlist waits.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import time
from typing import Callable
from urllib.parse import urlsplit

from readlist.model import Paper

EXECUTABLE = "browser-use"
SESSION = "readlist"
LOAD_TIMEOUT_SECONDS = 60  # long enough to click through a bot check by hand
SETTLED_PAGE_POLLS = 5  # a non-PDF, non-challenge page this many polls in a row: give up
POLL_SECONDS = 1.0
CHALLENGE_TITLES = re.compile(r"just a moment|attention required|verify|checking", re.IGNORECASE)
DOI_IN_URL = re.compile(r"^https?://(dx\.)?doi\.org/(10\.\d{4,9}/\S+)$", re.IGNORECASE)

# Started in the page; eval cannot await, so the result lands in a global we poll.
START_DOWNLOAD = """
window.__readlist_pdf = "pending";
fetch(location.href).then(async response => {
  const bytes = new Uint8Array(await response.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 32768) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
  }
  window.__readlist_pdf = response.status + " " + btoa(binary);
}).catch(error => { window.__readlist_pdf = "error " + error; });
"started";
"""

Run = Callable[[list[str]], str]


class BrowserError(Exception):
    pass


def available() -> bool:
    return shutil.which(EXECUTABLE) is not None


def candidate_urls(paper: Paper, *known: str | None) -> list[str]:
    """PDF links worth trying in a browser: known blocked links, then publisher patterns."""
    urls = [url for url in known if url and _looks_like_pdf(url)]

    doi = paper.doi or _doi_from(paper.landing)
    if doi.lower().startswith("10.1145/"):  # ACM Digital Library
        urls.append(f"https://dl.acm.org/doi/pdf/{doi}")
    if _looks_like_pdf(paper.landing):
        urls.append(paper.landing)

    return list(dict.fromkeys(urls))


class Browser:
    """A visible browser-use session. Use as a context manager so the window closes."""

    def __init__(
        self,
        run: Run | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._run = run or _run
        self._sleep = sleep
        self._clock = clock

    def __enter__(self) -> Browser:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def fetch_pdf(self, url: str) -> bytes:
        self._call("open", url)
        self._wait_for_pdf(url)

        self._eval(START_DOWNLOAD)
        result = self._wait_for_download(url)

        status, _, payload = result.partition(" ")
        if status != "200":
            raise BrowserError(f"{url}: {result[:80]}")
        return base64.b64decode(payload)

    def close(self) -> None:
        try:
            self._call("close")
        except BrowserError:
            pass  # already closed, or never opened

    def _wait_for_pdf(self, url: str) -> None:
        deadline = self._clock() + LOAD_TIMEOUT_SECONDS
        settled = 0
        while self._clock() < deadline:
            content_type, _, title = self._page_state().partition("\n")
            if content_type == "application/pdf":
                return
            elif content_type and not CHALLENGE_TITLES.search(title):
                settled += 1
                if settled >= SETTLED_PAGE_POLLS:
                    raise BrowserError(f"{url}: the browser shows a web page, not a PDF")
            else:
                settled = 0
            self._sleep(POLL_SECONDS)
        raise BrowserError(f"{url}: no PDF after {LOAD_TIMEOUT_SECONDS}s (bot check unsolved?)")

    def _wait_for_download(self, url: str) -> str:
        deadline = self._clock() + LOAD_TIMEOUT_SECONDS
        while self._clock() < deadline:
            result = self._eval("window.__readlist_pdf")
            if result != "pending":
                return result
            self._sleep(POLL_SECONDS)
        raise BrowserError(f"{url}: download did not finish in {LOAD_TIMEOUT_SECONDS}s")

    def _page_state(self) -> str:
        try:
            return self._eval("document.contentType + '\\n' + document.title")
        except BrowserError:
            return ""  # mid-navigation; try again

    def _eval(self, script: str) -> str:
        return str(self._call("eval", script))

    def _call(self, *arguments: str):
        output = self._run([EXECUTABLE, "--headed", "--session", SESSION, "--json", *arguments])
        try:
            reply = json.loads(output)
        except json.JSONDecodeError as problem:
            raise BrowserError(f"unexpected browser-use output: {output[:120]!r}") from problem
        if not reply.get("success"):
            raise BrowserError(f"browser-use {arguments[0]}: {reply.get('error') or reply}")
        data = reply.get("data")
        return data.get("result", "") if isinstance(data, dict) else data


def _run(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if completed.returncode != 0 and not completed.stdout.strip():
        raise BrowserError(completed.stderr.strip() or f"{command[0]} exited {completed.returncode}")
    return completed.stdout


def _looks_like_pdf(url: str) -> bool:
    if not url:
        return False
    path = urlsplit(url).path.lower()
    return path.endswith(".pdf") or "/pdf/" in path


def _doi_from(url: str) -> str:
    match = DOI_IN_URL.match(url or "")
    return match.group(2) if match else ""
