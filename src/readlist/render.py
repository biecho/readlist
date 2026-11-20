"""How readlist prints. Three views of the same entries:

terminal (stdout is a terminal):

    FRONTIER

       8  BadRAM: Practical Memory Aliasing Attacks on Trusted Execution Environments
          De Meulemeester et al. · IEEE S&P 2025 · core · downloaded · demeulemeester2025badram
          Read in full. $10 SPD trick -> address aliasing -> SEV-SNP integrity broken.

lines (stdout is a pipe): one tab-separated line per paper,
    number, id, status, section, title, path-or-link

json (--json): one JSON array.

Color only on a terminal, and never when NO_COLOR is set.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

from readlist.commands import Outcome, Result
from readlist.library import Availability, Library, State
from readlist.model import Entry, Paper

MAX_WIDTH = 100


# --- views of entries ----------------------------------------------------------

def terminal(entries: list[Entry], library: Library, style: Style, width: int) -> str:
    """Numbered papers under section headings."""
    number_width = max((len(str(e.number)) for e in entries), default=1)
    indent = " " * (2 + number_width + 2)

    blocks, section = [], None
    for entry in entries:
        if entry.section != section:
            section = entry.section
            if section:
                blocks.append(style.heading(section.upper()))
        blocks.append(_entry(entry, library.state(entry.paper), style, width, number_width, indent))
    return "\n\n".join(blocks)


def lines(entries: list[Entry], library: Library) -> str:
    rows = []
    for entry in entries:
        state = library.state(entry.paper)
        where = str(state.path) if state.path else state.link
        fields = (str(entry.number), entry.paper.id, state.availability.label, entry.section,
                  entry.paper.title, where)
        rows.append("\t".join(_one_line(f) for f in fields))
    return "\n".join(rows)


def as_json(entries: list[Entry], library: Library) -> str:
    records = []
    for entry in entries:
        paper, state = entry.paper, library.state(entry.paper)
        records.append({
            "number": entry.number, "id": paper.id, "title": paper.title,
            "section": entry.section, "group": paper.group, "authors": list(paper.authors),
            "year": paper.year, "venue": paper.venue, "kind": paper.kind,
            "tags": sorted(paper.tags), "status": state.availability.label,
            "path": str(state.path) if state.path else None, "link": state.link or None,
            "why": paper.why,
        })
    return json.dumps(records, indent=2, ensure_ascii=False)


def summary(entries: list[Entry], library: Library, style: Style) -> str:
    """'26 papers · 24 downloaded · 1 to fetch by hand · 1 link'."""
    counts = {a: 0 for a in Availability}
    for entry in entries:
        counts[library.state(entry.paper).availability] += 1

    parts = [f"{len(entries)} papers", style.green(f"{counts[Availability.DOWNLOADED]} downloaded")]
    if counts[Availability.FETCH_BY_HAND]:
        parts.append(style.yellow(f"{counts[Availability.FETCH_BY_HAND]} to fetch by hand"))
    if counts[Availability.NOT_FETCHED]:
        parts.append(style.red(f"{counts[Availability.NOT_FETCHED]} not fetched"))
    if counts[Availability.LINK]:
        n = counts[Availability.LINK]
        parts.append(style.dim(f"{n} {'link' if n == 1 else 'links'}"))
    return " · ".join(parts)


# --- fetch output --------------------------------------------------------------

RESULT_WIDTH = max(len(r.label) for r in Result)


def fetch_line(outcome: Outcome, id_width: int, style: Style) -> str:
    """'  got            schluter2024wesee   arxiv 2404.03526'."""
    label = outcome.result.label.ljust(RESULT_WIDTH)
    paper_id = outcome.entry.paper.id.ljust(id_width)
    return f"  {_result_color(outcome.result, style)(label)}  {paper_id}  {relative(outcome.detail)}"


def _result_color(result: Result, style: Style):
    if result is Result.GOT or result is Result.HAVE:
        return style.green
    elif result is Result.FETCH_BY_HAND or result is Result.WOULD_GET:
        return style.yellow
    elif result is Result.FAILED:
        return style.red
    elif result is Result.LINK:
        return style.dim
    else:
        raise AssertionError(f"unknown result {result}")


def relative(text: str) -> str:
    """Shorten absolute paths in `text` to paths relative to the current folder."""
    cwd = str(Path.cwd()) + os.sep
    return text.replace(cwd, "")


# --- terminal helpers ----------------------------------------------------------

def terminal_width() -> int:
    return min(shutil.get_terminal_size((MAX_WIDTH, 24)).columns, MAX_WIDTH)


def stdout_is_terminal() -> bool:
    return sys.stdout.isatty()


@dataclass(frozen=True)
class Style:
    color: bool

    @classmethod
    def for_stream(cls, stream) -> Style:
        return cls(color=stream.isatty() and "NO_COLOR" not in os.environ)

    def heading(self, text: str) -> str:
        return self._paint(text, "1;36")

    def bold(self, text: str) -> str:
        return self._paint(text, "1")

    def dim(self, text: str) -> str:
        return self._paint(text, "2")

    def green(self, text: str) -> str:
        return self._paint(text, "32")

    def yellow(self, text: str) -> str:
        return self._paint(text, "33")

    def red(self, text: str) -> str:
        return self._paint(text, "31")

    def cyan(self, text: str) -> str:
        return self._paint(text, "36")

    def _paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text


def _entry(entry: Entry, state: State, style: Style, width: int, number_width: int,
           indent: str) -> str:
    paper = entry.paper
    text_width = max(width - len(indent), 30)
    title = textwrap.wrap(paper.title, text_width) or [paper.id]

    out = [f"  {style.dim(str(entry.number).rjust(number_width))}  {style.bold(title[0])}"]
    out += [indent + style.bold(line) for line in title[1:]]
    out.append(indent + _meta(paper, state, style))
    out += [indent + line for line in textwrap.wrap(paper.why, text_width)]
    return "\n".join(out)


def _meta(paper: Paper, state: State, style: Style) -> str:
    plain = [short_authors(paper.authors),
             " ".join(part for part in (paper.venue, str(paper.year or "")) if part),
             paper.kind if paper.kind != "paper" else ""]
    parts = [style.dim(part) for part in plain if part]
    if "core" in paper.tags:
        parts.append(style.cyan("core"))
    parts.append(_status(state.availability, style))
    parts.append(style.dim(paper.id))
    return style.dim(" · ").join(parts)


def _status(availability: Availability, style: Style) -> str:
    if availability is Availability.DOWNLOADED:
        return style.green(availability.label)
    elif availability is Availability.FETCH_BY_HAND:
        return style.yellow(availability.label)
    elif availability is Availability.NOT_FETCHED:
        return style.red(availability.label)
    elif availability is Availability.LINK:
        return style.dim(availability.label)
    else:
        raise AssertionError(f"unknown availability {availability}")


def short_authors(authors: tuple[str, ...]) -> str:
    """'Li et al.', 'Costan & Devadas', 'Van Bulck'."""
    names = [a for a in authors if a.strip().lower() not in ("et al.", "et al", "others")]
    truncated = len(names) < len(authors)
    surnames = [_surname(name) for name in names]

    if not surnames:
        return ""
    elif len(surnames) == 1 and not truncated:
        return surnames[0]
    elif len(surnames) == 2 and not truncated:
        return f"{surnames[0]} & {surnames[1]}"
    else:
        return f"{surnames[0]} et al."


def _surname(name: str) -> str:
    """'Costan, Victor' -> 'Costan'; 'Jo Van Bulck' -> 'Van Bulck'; 'AMD' -> 'AMD'."""
    if "," in name:
        return name.split(",", 1)[0].strip()
    words = name.split()
    particles = {"van", "von", "de", "der", "den", "du", "da", "di", "la", "le"}
    start = len(words) - 1
    while start > 0 and words[start - 1].lower() in particles:
        start -= 1
    return " ".join(words[start:])


def _one_line(text: str) -> str:
    return " ".join(text.split())
