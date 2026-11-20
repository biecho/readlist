import base64
import json
from dataclasses import replace

import pytest

from conftest import PDF, FakeHttp
from readlist import browser, commands
from readlist.config import Config
from readlist.library import Library
from readlist.model import Paper, ReadingList


class FakeBrowserUse:
    """Plays browser-use: pages per URL, as a sequence of (contentType, title) states."""

    def __init__(self, pages: dict[str, list[tuple[str, str]]], body: bytes = PDF, status=200):
        self.pages = pages
        self.body = body
        self.status = status
        self.calls: list[list[str]] = []
        self.states: list[tuple[str, str]] = []

    def __call__(self, command: list[str]) -> str:
        self.calls.append(command)
        action, *rest = command[command.index("--json") + 1:]
        if action == "open":
            self.states = list(self.pages.get(rest[0], [("text/html", "Not found")]))
            return self._ok("")
        elif action == "close":
            return self._ok("")
        elif "contentType" in rest[0]:
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return self._ok("\n".join(state))
        elif "fetch(location.href)" in rest[0]:
            return self._ok("started")
        elif rest[0] == "window.__readlist_pdf":
            return self._ok(f"{self.status} {base64.b64encode(self.body).decode()}")
        else:
            raise AssertionError(f"unexpected call {command}")

    def opened(self) -> list[str]:
        return [c[-1] for c in self.calls if "open" in c]

    @staticmethod
    def _ok(result: str) -> str:
        return json.dumps({"success": True, "data": {"result": result}})


def make_browser(fake: FakeBrowserUse) -> browser.Browser:
    clock = iter(range(10_000))
    return browser.Browser(run=fake, sleep=lambda seconds: None, clock=lambda: next(clock))


ACM_PDF = "https://dl.acm.org/doi/pdf/10.1145/1.2"
CHALLENGE_THEN_PDF = [("text/html", "Just a moment..."), ("application/pdf", "")]


def test_waits_through_bot_check_then_downloads():
    fake = FakeBrowserUse({ACM_PDF: CHALLENGE_THEN_PDF})
    assert make_browser(fake).fetch_pdf(ACM_PDF) == PDF


def test_gives_up_on_a_plain_web_page():
    fake = FakeBrowserUse({ACM_PDF: [("text/html", "Article page")]})
    with pytest.raises(browser.BrowserError, match="web page, not a PDF"):
        make_browser(fake).fetch_pdf(ACM_PDF)


def test_candidate_urls_add_acm_pattern_and_skip_web_pages():
    paper = Paper(id="p", title="T", landing="https://doi.org/10.1145/1.2")
    assert browser.candidate_urls(paper, "https://site.org/page", "https://x.org/a.pdf") == [
        "https://x.org/a.pdf", ACM_PDF]


def run_fetch(tmp_path, paper, http, fake):
    reading_list = ReadingList(source=tmp_path / "l.yaml", papers=(paper,))
    return commands.fetch(reading_list, Library(tmp_path / "papers"), http, Config(),
                          browser=make_browser(fake) if fake else None)


def test_paper_without_open_copy_comes_through_the_browser(tmp_path):
    paper = Paper(id="p", title="T", group="g", number=1, doi="10.1145/1.2", open_copy=False)
    fake = FakeBrowserUse({ACM_PDF: CHALLENGE_THEN_PDF})
    [outcome] = run_fetch(tmp_path, paper, FakeHttp(), fake)
    assert outcome.status == "got" and outcome.detail == f"browser: {ACM_PDF}"
    assert (tmp_path / "papers/g/p.pdf").read_bytes() == PDF


def test_blocked_list_link_retried_in_browser(tmp_path):
    paper = Paper(id="p", title="T", pdf=ACM_PDF)
    fake = FakeBrowserUse({ACM_PDF: CHALLENGE_THEN_PDF})
    [outcome] = run_fetch(tmp_path, paper, FakeHttp({ACM_PDF: 403}), fake)
    assert outcome.status == "got" and fake.opened() == [ACM_PDF]


def test_without_browser_flag_behaviour_is_unchanged(tmp_path):
    paper = Paper(id="p", title="T", pdf=ACM_PDF)
    [outcome] = run_fetch(tmp_path, paper, FakeHttp({ACM_PDF: 403}), None)
    assert outcome.status == "failed"


def test_browser_failure_leaves_placeholder_with_note(tmp_path):
    paper = Paper(id="p", title="T", doi="10.1145/1.2", landing="https://landing", open_copy=False)
    fake = FakeBrowserUse({ACM_PDF: CHALLENGE_THEN_PDF}, status=403)
    [outcome] = run_fetch(tmp_path, paper, FakeHttp(), fake)
    assert outcome.status == "manual" and "browser:" in outcome.detail
    assert "URL=https://landing" in (tmp_path / "papers/p.url").read_text()


def test_talks_never_open_the_browser(tmp_path):
    paper = replace(Paper(id="t", title="Talk", kind="talk"), landing="https://x.org/slides.pdf")
    fake = FakeBrowserUse({})
    [outcome] = run_fetch(tmp_path, paper, FakeHttp(), fake)
    assert outcome.status == "manual" and fake.opened() == []
