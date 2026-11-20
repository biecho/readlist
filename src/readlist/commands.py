"""What readlist does, without the command line: testable with fakes."""

from __future__ import annotations

import enum
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from readlist import resolvers, writeback
from readlist.browser import Browser, BrowserError, candidate_urls
from readlist.config import Config
from readlist.http import Fetcher, HttpError
from readlist.library import Availability, Library, NotAPdf
from readlist.model import ARXIV_ID, Entry, ReadingList, SelectionError
from readlist.resolvers import Resolution, arxiv

DOI = re.compile(r"^10\.\d{4,9}/\S+$")
# Hosts that refuse scripts but serve browsers (ACM, IEEE, ePrint bot checks).
BLOCKED_STATUSES = {401, 403}
OPEN_LIMIT = 10  # opening more papers at once, by filter alone, needs allow_many


# --- fetch -------------------------------------------------------------------

class Result(enum.Enum):
    GOT = "got"
    WOULD_GET = "would get"
    HAVE = "have"
    LINK = "link"
    FETCH_BY_HAND = "fetch by hand"
    FAILED = "failed"

    @property
    def label(self) -> str:
        return self.value


@dataclass(frozen=True)
class Outcome:
    entry: Entry
    result: Result
    detail: str = ""


@dataclass(frozen=True)
class FetchOptions:
    force: bool = False  # re-download PDFs you have (annotated copies are backed up)
    dry_run: bool = False  # resolve links, change nothing
    record_into: Path | None = None  # write discovered links back into this list file


def fetch(
    entries: list[Entry],
    library: Library,
    http: Fetcher,
    config: Config,
    options: FetchOptions = FetchOptions(),
    browser: Browser | None = None,
    report: Callable[[Outcome], None] = lambda outcome: None,
) -> list[Outcome]:
    """Download each paper. With `browser`, retry papers a site blocks in a visible browser."""
    outcomes = []
    for entry in entries:
        outcome = _Fetch(entry, library, http, config, options, browser).run()
        report(outcome)
        outcomes.append(outcome)
    return outcomes


class _Fetch:
    """Fetching one paper: find an open copy, download it, or leave a link."""

    def __init__(self, entry, library, http, config, options, browser):
        self.entry = entry
        self.paper = entry.paper
        self.library = library
        self.http = http
        self.config = config
        self.options = options
        self.browser = browser

    def run(self) -> Outcome:
        if not self.options.dry_run:
            self.library.sync(self.paper)

        state = self.library.state(self.paper)
        if state.availability is Availability.DOWNLOADED and not self.options.force:
            return self._outcome(Result.HAVE, str(state.path))
        elif self.paper.link_only:
            return self._outcome(Result.LINK, self.paper.landing)

        earlier_link = self.library.blocked_link(self.paper)
        try:
            resolution = resolvers.resolve(self.paper, self.http, self.config)
        except resolvers.ResolveError as problem:
            return self._outcome(Result.FAILED, str(problem))
        except HttpError as problem:
            return self._outcome(Result.FAILED, f"lookup: {problem}")

        if resolution is None:
            return self._no_open_copy(earlier_link)
        elif self.options.dry_run:
            return self._outcome(Result.WOULD_GET, f"{resolution.source}: {resolution.url}")
        else:
            return self._download(resolution, earlier_link)

    def _download(self, resolution: Resolution, earlier_link: str) -> Outcome:
        try:
            backup = self.library.store(self.paper, self.http.get(resolution.url), resolution.url)
        except HttpError as problem:
            if problem.status in BLOCKED_STATUSES:
                return self._blocked(resolution, earlier_link, problem)
            return self._outcome(Result.FAILED, f"{resolution.url}: {problem}")
        except NotAPdf as problem:
            return self._outcome(Result.FAILED, f"{resolution.url}: {problem}")

        notes = [resolution.source]
        if backup is not None:
            notes.append(f"kept annotated copy at {backup}")
        if self.options.record_into is not None and resolution.discovered:
            notes.append(self._record(resolution.url))
        return self._outcome(Result.GOT, "; ".join(notes))

    def _no_open_copy(self, earlier_link: str) -> Outcome:
        if self.options.dry_run:
            return self._outcome(Result.FETCH_BY_HAND, "no open copy found")

        got, tried = self._via_browser(earlier_link)
        if got is not None:
            return got
        placeholder = self.library.write_placeholder(self.paper)
        return self._outcome(Result.FETCH_BY_HAND, f"{placeholder}{tried}")

    def _blocked(self, resolution: Resolution, earlier_link: str, problem: HttpError) -> Outcome:
        """The host refused the script. Try the browser, else leave a link to the copy."""
        got, tried = self._via_browser(resolution.url, earlier_link)
        if got is not None:
            return got
        elif resolution.discovered:
            placeholder = self.library.write_placeholder(self.paper, resolution.url)
            return self._outcome(Result.FETCH_BY_HAND,
                                 f"{placeholder} (the site blocks scripts){tried}")
        else:
            return self._outcome(Result.FAILED, f"{resolution.url}: {problem}{tried}")

    def _via_browser(self, *known_links: str) -> tuple[Outcome | None, str]:
        """(outcome if a browser download worked, else a note on what was tried)."""
        if self.browser is None or not self.paper.may_use_browser:
            return None, ""
        urls = candidate_urls(self.paper, *known_links)
        if not urls:
            return None, " (browser: no PDF link to try)"

        problems = []
        for url in urls:
            try:
                self.library.store(self.paper, self.browser.fetch_pdf(url), url)
            except (BrowserError, NotAPdf) as problem:
                problems.append(str(problem))
                continue
            return self._outcome(Result.GOT, f"browser: {url}"), ""
        return None, f" (browser: {'; '.join(problems)})"

    def _record(self, url: str) -> str:
        list_path = self.options.record_into
        try:
            writeback.record_pdf_link(list_path, self.paper.id, url)
        except writeback.WritebackError as problem:
            return f"not recorded: {problem}"
        return f"recorded in {list_path.name}"

    def _outcome(self, result: Result, detail: str = "") -> Outcome:
        return Outcome(self.entry, result, detail)


# --- open --------------------------------------------------------------------

class Opened(enum.Enum):
    PDF = "pdf"
    LINK = "link"  # a talk or web page
    FETCH_BY_HAND = "fetch by hand"  # the page where you can get it
    NOT_FETCHED = "not fetched"


@dataclass(frozen=True)
class OpenResult:
    entry: Entry
    opened: Opened
    target: str = ""


def check_open_count(entries: list[Entry], *, picked: bool, allow_many: bool) -> None:
    """Refuse to open a flood of windows by accident."""
    if not entries:
        raise SelectionError("nothing to open")
    if not picked and len(entries) > OPEN_LIMIT and not allow_many:
        raise SelectionError(f"that selects {len(entries)} papers; "
                             f"name them by number, or add --all")


def open_entries(
    entries: list[Entry],
    library: Library,
    open_pdf: Callable[[Path], None],
    open_url: Callable[[str], None],
) -> list[OpenResult]:
    """PDFs open in the PDF app; links and fetch-by-hand pages in the browser."""
    results = []
    for entry in entries:
        state = library.state(entry.paper)
        if state.availability is Availability.DOWNLOADED:
            open_pdf(state.path)
            results.append(OpenResult(entry, Opened.PDF, str(state.path)))
        elif state.availability is Availability.LINK and state.link:
            open_url(state.link)
            results.append(OpenResult(entry, Opened.LINK, state.link))
        elif state.availability is Availability.FETCH_BY_HAND and state.link:
            open_url(state.link)
            results.append(OpenResult(entry, Opened.FETCH_BY_HAND, state.link))
        else:
            results.append(OpenResult(entry, Opened.NOT_FETCHED))
    return results


# --- check -------------------------------------------------------------------

def check(reading_list: ReadingList, http: Fetcher | None = None) -> list[str]:
    """Problems in the list. With `http`, also verify every arXiv id against its title."""
    problems = [f"{i}: duplicate id" for i, n in Counter(p.id for p in reading_list.papers).items()
                if n > 1]
    problems += reading_list.ranking_problems()

    for paper in reading_list.papers:
        problems += [f"{paper.id}: {problem}" for problem in _field_problems(paper)]
        if http is not None and paper.arxiv and ARXIV_ID.match(paper.arxiv):
            try:
                arxiv.resolve_id(paper, http, Config())
            except resolvers.ResolveError as problem:
                problems.append(f"{paper.id}: {problem}")
    return problems


def _field_problems(paper) -> list[str]:
    problems = []
    if paper.arxiv and not ARXIV_ID.match(paper.arxiv):
        problems.append(f"'{paper.arxiv}' is not an arXiv id")
    if paper.doi and not DOI.match(paper.doi):
        problems.append(f"'{paper.doi}' is not a DOI (expected 10.xxxx/...)")
    for name in ("pdf", "landing"):
        value = getattr(paper, name)
        if value and not value.startswith(("https://", "http://")):
            problems.append(f"{name} '{value}' is not an http(s) link")
    return problems
