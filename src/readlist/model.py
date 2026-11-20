"""The reading list as plain data. No I/O, no formats, no network."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

# New-style (2404.03387) and old-style (cs/0112017) arXiv ids, optional version.
ARXIV_ID = re.compile(r"^(\d{4}\.\d{4,5}|[a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?$")

# Kinds that are never downloaded: they always get a link placeholder.
LINK_ONLY_KINDS = frozenset({"talk", "web"})


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    group: str = ""
    number: int | None = None  # filename prefix, e.g. reading order or citation number
    authors: tuple[str, ...] = ()
    year: int | None = None
    venue: str = ""
    kind: str = "paper"
    tags: frozenset[str] = frozenset()
    pdf: str = ""  # direct link to an open copy
    arxiv: str = ""
    doi: str = ""
    landing: str = ""  # human-facing page, used for placeholders
    open_copy: bool = True  # False: the only acceptable copy is an explicit `pdf`

    @property
    def stem(self) -> str:
        """Filename without extension."""
        if self.number is None:
            return self.id
        return f"{self.number:02d}-{self.id}"

    @property
    def downloadable(self) -> bool:
        return self.kind not in LINK_ONLY_KINDS

    def with_group(self, group: str) -> Paper:
        return replace(self, group=group)


@dataclass(frozen=True)
class ReadingList:
    source: Path
    papers: tuple[Paper, ...] = field(default_factory=tuple)

    def select(self, *, group: str | None = None, tag: str | None = None) -> ReadingList:
        papers = self.papers
        if group is not None:
            papers = tuple(p for p in papers if p.group == group)
        if tag is not None:
            papers = tuple(p for p in papers if tag in p.tags)
        return replace(self, papers=papers)

    def groups(self) -> list[str]:
        """Group names in order of first appearance."""
        return list(dict.fromkeys(p.group for p in self.papers))


class FormatError(ValueError):
    """The reading list file is malformed."""
