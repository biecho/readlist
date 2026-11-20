"""The reading list as plain data. No I/O, no formats, no network.

Every paper has exactly one number: its place in the reading order. The
reading order is the list's `ranking` when it has one (papers the ranking
leaves out follow at the end), and the order of the file otherwise. Filters
never renumber, so number 8 is the same paper in every command.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

# New-style (2404.03387) and old-style (cs/0112017) arXiv ids, optional version.
ARXIV_ID = re.compile(r"^(\d{4}\.\d{4,5}|[a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?$")

# Kinds readlist never searches for: only an explicit `pdf` link (e.g. slides) downloads.
LINK_KINDS = frozenset({"talk", "web"})
UNRANKED_SECTION = "Not ranked"


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    group: str = ""  # folder under papers/
    authors: tuple[str, ...] = ()
    year: int | None = None
    venue: str = ""
    kind: str = "paper"
    tags: frozenset[str] = frozenset()
    pdf: str = ""  # direct link to an open copy
    arxiv: str = ""
    doi: str = ""
    landing: str = ""  # human-facing page, used for placeholders
    why: str = ""  # why read it (`why` or `read_for` in YAML)
    open_copy: bool = True  # False: online lookups would find another version

    @property
    def link_only(self) -> bool:
        """A talk or web page without a `pdf` link: nothing to fetch, only a link."""
        return self.kind in LINK_KINDS and not self.pdf

    @property
    def may_look_up(self) -> bool:
        """Whether arXiv, Unpaywall and Semantic Scholar may be asked for a copy."""
        return self.kind not in LINK_KINDS and self.open_copy

    @property
    def may_use_browser(self) -> bool:
        """Whether a browser may fetch the publisher's own PDF."""
        return self.kind not in LINK_KINDS

    def with_group(self, group: str) -> Paper:
        return replace(self, group=group)


@dataclass(frozen=True)
class Section:
    """A stretch of the ranking, e.g. 'Map' or 'Frontier'. The title may be empty."""

    title: str
    ids: tuple[str, ...]


@dataclass(frozen=True)
class Entry:
    """A paper in its place: reading-order number and the section it is shown under."""

    number: int
    paper: Paper
    section: str


@dataclass(frozen=True)
class ReadingList:
    source: Path
    papers: tuple[Paper, ...] = field(default_factory=tuple)
    ranking: tuple[Section, ...] = ()  # read-first to read-last
    group_titles: Mapping[str, str] = field(default_factory=dict)

    def entries(self) -> list[Entry]:
        """Every paper in reading order, numbered from 1."""
        placed = self._ranked() if self.ranking else self._by_group()
        return [Entry(n, paper, section) for n, (paper, section) in enumerate(placed, start=1)]

    def ranking_problems(self) -> list[str]:
        """Ids the ranking names but the list lacks, repeats, or leaves out."""
        if not self.ranking:
            return []
        ranked = [i for section in self.ranking for i in section.ids]
        known = {p.id for p in self.papers}
        problems = [f"ranking names unknown id '{i}'" for i in dict.fromkeys(ranked) if i not in known]
        problems += [f"ranking repeats '{i}'" for i, n in Counter(ranked).items() if n > 1]
        problems += [f"'{p.id}' is not in the ranking" for p in self.papers if p.id not in set(ranked)]
        return problems

    def _ranked(self) -> list[tuple[Paper, str]]:
        by_id = {p.id: p for p in self.papers}
        placed, seen = [], set()
        for section in self.ranking:
            for paper_id in section.ids:
                if paper_id in by_id and paper_id not in seen:
                    placed.append((by_id[paper_id], section.title))
                    seen.add(paper_id)
        placed += [(p, UNRANKED_SECTION) for p in self.papers if p.id not in seen]
        return placed

    def _by_group(self) -> list[tuple[Paper, str]]:
        groups = dict.fromkeys(p.group for p in self.papers)
        return [(p, self.group_titles.get(g) or g) for g in groups for p in self.papers
                if p.group == g]


class FormatError(ValueError):
    """The reading list file is malformed."""


class SelectionError(ValueError):
    """A selector names nothing in the list."""


def select(reading_list: ReadingList, *, section: str | None = None,
           tag: str | None = None) -> list[Entry]:
    """Entries in `section` and with `tag`. A selector that matches nothing is an error.

    `section` matches, ignoring case, a ranking section title, a group id or a
    group title, so `-s map` finds the 'Map' section or the group '01-map'.
    """
    entries = reading_list.entries()
    if section is not None:
        entries = [e for e in entries if _in_section(e, section, reading_list)]
        if not entries:
            raise SelectionError(f"no section or group '{section}' "
                                 f"(choose from: {', '.join(section_names(reading_list))})")
    if tag is not None:
        entries = [e for e in entries if tag in e.paper.tags]
        if not entries:
            tags = sorted({t for p in reading_list.papers for t in p.tags}) or ["none"]
            raise SelectionError(f"no paper tagged '{tag}' here (tags: {', '.join(tags)})")
    return entries


def pick(reading_list: ReadingList, selectors: list[str]) -> list[Entry]:
    """Entries named by number ('4'), range ('4-8') or id, in reading order."""
    entries = reading_list.entries()
    by_number = {e.number: e for e in entries}
    by_id = {e.paper.id: e for e in entries}

    picked: dict[int, Entry] = {}
    for selector in selectors:
        for entry in _expand(selector, by_number, by_id):
            picked[entry.number] = entry
    return [picked[n] for n in sorted(picked)]


def section_names(reading_list: ReadingList) -> list[str]:
    names = [s.title for s in reading_list.ranking if s.title]
    names += [g for g in dict.fromkeys(p.group for p in reading_list.papers) if g]
    return list(dict.fromkeys(names))


def _in_section(entry: Entry, name: str, reading_list: ReadingList) -> bool:
    wanted = name.lower()
    group = entry.paper.group
    candidates = (entry.section, group, reading_list.group_titles.get(group, ""))
    return any(c and c.lower() == wanted for c in candidates)


def _expand(selector: str, by_number: dict[int, Entry], by_id: dict[str, Entry]) -> list[Entry]:
    if selector in by_id:
        return [by_id[selector]]

    low, dash, high = selector.partition("-")
    if not (low.isdigit() and (not dash or high.isdigit())):
        raise SelectionError(f"'{selector}' is neither a paper id nor a number")

    first, last = int(low), int(high) if dash else int(low)
    numbers = range(first, last + 1)
    if first > last or any(n not in by_number for n in numbers):
        raise SelectionError(f"'{selector}': numbers run from 1 to {len(by_number)}")
    return [by_number[n] for n in numbers]
