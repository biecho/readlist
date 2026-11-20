"""What the CLI does, without the CLI: testable with a fake Fetcher."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from readlist import resolvers, writeback
from readlist.browser import Browser, BrowserError, candidate_urls
from readlist.config import Config
from readlist.http import Fetcher, HttpError
from readlist.library import Library, NotAPdf
from readlist.model import ARXIV_ID, Paper, ReadingList
from readlist.resolvers import arxiv

DOI = re.compile(r"^10\.\d{4,9}/\S+$")
# Hosts that refuse scripts but serve browsers (ACM, IEEE, ePrint bot checks).
BLOCKED_STATUSES = {401, 403}


@dataclass(frozen=True)
class Outcome:
    paper: Paper
    status: str  # have | got | would | manual | failed
    detail: str = ""


def fetch(
    reading_list: ReadingList,
    library: Library,
    http: Fetcher,
    config: Config,
    *,
    force: bool = False,
    dry_run: bool = False,
    record: bool = False,
    browser: Browser | None = None,
    report: Callable[[Outcome], None] = lambda outcome: None,
) -> list[Outcome]:
    """Download each paper. With `browser`, retry blocked papers in a visible browser."""
    outcomes = []
    for paper in reading_list.papers:
        outcome = _fetch_one(paper, reading_list, library, http, config,
                             force=force, dry_run=dry_run, record=record, browser=browser)
        report(outcome)
        outcomes.append(outcome)
    return outcomes


def check(reading_list: ReadingList, http: Fetcher | None = None) -> list[str]:
    """Problems in the list. With `http`, also verify every arXiv id against its title."""
    problems = []
    duplicates = [i for i, n in Counter(p.id for p in reading_list.papers).items() if n > 1]
    problems += [f"{i}: duplicate id" for i in duplicates]

    for paper in reading_list.papers:
        problems += [f"{paper.id}: {problem}" for problem in _offline_problems(paper)]
        if http is not None and paper.arxiv and ARXIV_ID.match(paper.arxiv):
            try:
                arxiv.resolve_id(paper, http, Config())
            except resolvers.ResolveError as problem:
                problems.append(f"{paper.id}: {problem}")
    return problems


def _fetch_one(paper, reading_list, library, http, config, *,
               force, dry_run, record, browser) -> Outcome:
    if library.has(paper) and not force:
        return Outcome(paper, "have", str(library.pdf_path(paper)))
    earlier_link = library.placeholder_target(paper)  # a blocked link from an earlier run

    try:
        resolution = resolvers.resolve(paper, http, config)
    except resolvers.ResolveError as problem:
        return Outcome(paper, "failed", str(problem))
    except HttpError as problem:
        return Outcome(paper, "failed", f"lookup: {problem}")

    if resolution is None:
        return _no_open_copy(paper, library, browser, dry_run, earlier_link)
    elif dry_run:
        return Outcome(paper, "would", f"{resolution.source}: {resolution.url}")

    try:
        body = http.get(resolution.url)
        backup = library.store(paper, body, resolution.url)
    except HttpError as problem:
        if problem.status in BLOCKED_STATUSES:
            return _blocked(paper, library, browser, resolution, earlier_link, problem)
        return Outcome(paper, "failed", f"{resolution.url}: {problem}")
    except NotAPdf as problem:
        return Outcome(paper, "failed", f"{resolution.url}: {problem}")

    notes = [resolution.source]
    if backup is not None:
        notes.append(f"kept annotated copy at {backup}")
    if record and resolution.discovered:
        notes.append(_record(reading_list, paper, resolution.url))
    return Outcome(paper, "got", "; ".join(notes))


def _no_open_copy(paper, library, browser, dry_run, earlier_link) -> Outcome:
    if dry_run:
        return Outcome(paper, "manual", "no open copy found")

    tried = ""
    if browser is not None and paper.searchable:
        outcome, tried = _via_browser(paper, library, browser, earlier_link)
        if outcome is not None:
            return outcome

    placeholder = library.write_placeholder(paper)
    return Outcome(paper, "manual", f"{placeholder}{tried}")


def _blocked(paper, library, browser, resolution, earlier_link, problem) -> Outcome:
    """The host refused the script. Try the browser, else leave a link to the copy."""
    tried = ""
    if browser is not None:
        outcome, tried = _via_browser(paper, library, browser, resolution.url, earlier_link)
        if outcome is not None:
            return outcome

    if resolution.discovered:
        placeholder = library.write_placeholder(paper, resolution.url)
        return Outcome(paper, "manual",
                       f"{placeholder} (host blocks scripts; open copy found){tried}")
    return Outcome(paper, "failed", f"{resolution.url}: {problem}{tried}")


def _via_browser(paper, library, browser, *known_links) -> tuple[Outcome | None, str]:
    """(outcome if a browser download worked, else a note on what was tried)."""
    urls = candidate_urls(paper, *known_links)
    if not urls:
        return None, " (browser: no PDF link to try)"

    problems = []
    for url in urls:
        try:
            library.store(paper, browser.fetch_pdf(url), url)
        except (BrowserError, NotAPdf) as problem:
            problems.append(str(problem))
            continue
        return Outcome(paper, "got", f"browser: {url}"), ""
    return None, f" (browser: {'; '.join(problems)})"


def _record(reading_list: ReadingList, paper: Paper, url: str) -> str:
    try:
        writeback.record_pdf_link(reading_list.source, paper.id, url)
    except writeback.WritebackError as problem:
        return f"not recorded: {problem}"
    return f"recorded in {reading_list.source.name}"


def _offline_problems(paper: Paper) -> list[str]:
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
