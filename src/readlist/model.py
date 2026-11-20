"""The reading list as plain data. No I/O, no formats, no network."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

# New-style (2404.03387) and old-style (cs/0112017) arXiv ids, optional version.
ARXIV_ID = re.compile(r"^(\d{4}\.\d{4,5}|[a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?$")

# Kinds readlist never looks up: only an explicit `pdf` link (e.g. slides) downloads.
LINK_ONLY_KINDS = frozenset({"talk", "web"})


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    group: str = ""
    number: int | None = None  # position in its group, or citation number (display only)
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
    open_copy: bool = True  # False: the only acceptable copy is an explicit `pdf`

    @property
    def link_only(self) -> bool:
        """A talk or web page without a `pdf` link: there is nothing to fetch, only a link."""
        return self.kind in LINK_ONLY_KINDS and not self.pdf

    @property
    def searchable(self) -> bool:
        """Whether readlist may look for a copy beyond an explicit `pdf` link."""
        return self.kind not in LINK_ONLY_KINDS

    def with_group(self, group: str) -> Paper:
        return replace(self, group=group)


@dataclass(frozen=True)
class Section:
    """A stretch of the ranking, e.g. 'Map' or 'Frontier'. The title may be empty."""

    title: str
    ids: tuple[str, ...]


@dataclass(frozen=True)
class ReadingList:
    source: Path
    papers: tuple[Paper, ...] = field(default_factory=tuple)
    ranking: tuple[Section, ...] = ()  # read-first to read-last
    group_titles: Mapping[str, str] = field(default_factory=dict)

    def select(self, *, group: str | None = None, tag: str | None = None,
               section: str | None = None) -> ReadingList:
        papers = self.papers
        if group is not None:
            papers = tuple(p for p in papers if p.group == group)
        if tag is not None:
            papers = tuple(p for p in papers if tag in p.tags)
        if section is not None:
            in_section = set(self._section(section).ids)
            papers = tuple(p for p in papers if p.id in in_section)

        kept = {p.id for p in papers}
        sections = (Section(s.title, tuple(i for i in s.ids if i in kept)) for s in self.ranking)
        return replace(self, papers=papers, ranking=tuple(s for s in sections if s.ids))

    def positions(self) -> dict[str, int]:
        """Reading-order number per paper id, 1-based; unranked papers follow."""
        sections, unranked = self.ranked()
        ordered = [p for _, papers in sections for p in papers] + unranked
        return {p.id: n for n, p in enumerate(ordered, start=1)}

    def pick(self, selectors: list[str]) -> list[Paper]:
        """Papers named by reading-order number ('4'), range ('4-8') or id, in that order."""
        positions = self.positions()
        by_number = {n: i for i, n in positions.items()}
        by_id = {p.id: p for p in self.papers}

        picked: list[Paper] = []
        for selector in selectors:
            for paper_id in _expand(selector, by_number, by_id):
                if by_id[paper_id] not in picked:
                    picked.append(by_id[paper_id])
        return picked

    def ranked_ids(self) -> tuple[str, ...]:
        return tuple(i for section in self.ranking for i in section.ids)

    def ranked(self) -> tuple[list[tuple[str, list[Paper]]], list[Paper]]:
        """([(section title, papers)] in reading order, papers the ranking leaves out).

        Without a ranking, the groups in list order are the ranking.
        """
        if not self.ranking:
            return self.by_group(), []
        by_id = {p.id: p for p in self.papers}
        sections = [(s.title, [by_id[i] for i in s.ids]) for s in self.ranking]
        ranked = set(self.ranked_ids())
        return sections, [p for p in self.papers if p.id not in ranked]

    def _section(self, title: str) -> Section:
        for section in self.ranking:
            if section.title.lower() == title.lower():
                return section
        names = ", ".join(s.title for s in self.ranking if s.title) or "none"
        raise SelectionError(f"no ranking section '{title}' (sections: {names})")

    def by_group(self) -> list[tuple[str, list[Paper]]]:
        """[(group title, papers)] in list order."""
        groups = dict.fromkeys(p.group for p in self.papers)
        return [(self.group_titles.get(g) or g, [p for p in self.papers if p.group == g])
                for g in groups]


class FormatError(ValueError):
    """The reading list file is malformed."""


class SelectionError(ValueError):
    """A selector names nothing in the list."""


def _expand(selector: str, by_number: dict[int, str], by_id: dict[str, Paper]) -> list[str]:
    if selector in by_id:
        return [selector]

    low, dash, high = selector.partition("-")
    if low.isdigit() and (not dash or high.isdigit()):
        first, last = int(low), int(high) if dash else int(low)
        missing = [n for n in range(first, last + 1) if n not in by_number]
        if missing or first > last:
            raise SelectionError(f"'{selector}': no paper at position {missing[0] if missing else first}"
                                 f" (positions run 1-{len(by_number)})")
        return [by_number[n] for n in range(first, last + 1)]

    raise SelectionError(f"'{selector}' is neither a paper id nor a position")
