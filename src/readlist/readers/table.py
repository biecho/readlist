"""CSV reading lists: one row per paper.

Columns (header names; only id and title are required):
  id (or citekey/key), title, group (or cluster/stage), authors (separated by ;),
  year, venue, kind, tags (separated by ;), pdf, arxiv, doi, landing, open_copy
"""

from __future__ import annotations

import csv
from pathlib import Path

from readlist.model import FormatError, Paper, ReadingList

KEY_COLUMNS = ("id", "citekey", "key")
GROUP_COLUMNS = ("group", "cluster", "stage")
FALSE_WORDS = {"false", "no", "none", "0"}


def read_csv(path: Path) -> ReadingList:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    papers = tuple(_paper(row, path, line) for line, row in enumerate(rows, start=2))
    return ReadingList(source=path, papers=papers)


def _paper(row: dict[str, str], path: Path, line: int) -> Paper:
    row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    key = _first(row, KEY_COLUMNS)
    if not key or not row.get("title"):
        raise FormatError(f"{path}:{line}: needs an id and a title")

    return Paper(
        id=key,
        title=row["title"],
        group=_first(row, GROUP_COLUMNS),
        authors=_split(row.get("authors", "")),
        year=int(row["year"]) if row.get("year", "").isdigit() else None,
        venue=row.get("venue", ""),
        kind=row.get("kind") or "paper",
        tags=frozenset(_split(row.get("tags", ""))),
        pdf=row.get("pdf", ""),
        arxiv=row.get("arxiv", ""),
        doi=row.get("doi", ""),
        landing=row.get("landing", ""),
        open_copy=row.get("open_copy", "").lower() not in FALSE_WORDS,
    )


def _first(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        if row.get(name):
            return row[name]
    return ""


def _split(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(";") if part.strip())
