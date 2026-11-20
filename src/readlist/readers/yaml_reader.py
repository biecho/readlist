"""YAML reading lists.

Either grouped:

    groups:            # `stages:` is accepted as an alias
      - id: 01-basics
        title: Start here
        papers:
          - id: costan2016sgx
            title: Intel SGX Explained
            pdf: https://...

or flat, with a top-level `papers:` list. Papers are numbered by their
position within their group; the number prefixes the filename. Unknown keys
(reading notes, say) are ignored.

An optional top-level `ranking:` lists paper ids from read-first to
read-last, across groups; `readlist rank` shows it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from readlist.model import FormatError, Paper, ReadingList

def read_yaml(path: Path) -> ReadingList:
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise FormatError(f"{path}: top level must be a mapping")

    groups = data.get("groups", data.get("stages"))
    if groups is not None:
        papers = _grouped(groups, path)
    elif "papers" in data:
        papers = _numbered(data["papers"], group="", path=path)
    else:
        raise FormatError(f"{path}: needs a top-level 'groups' (or 'stages') or 'papers' list")

    ranking = _ranking(data.get("ranking"), papers, path)
    return ReadingList(source=path, papers=tuple(papers), ranking=ranking)


def _ranking(entries, papers: list[Paper], path: Path) -> tuple[str, ...]:
    """The top-level `ranking:`, a list of paper ids. Every id must exist, once."""
    if entries is None:
        return ()
    ranking = tuple(str(entry) for entry in entries)
    known = {p.id for p in papers}

    unknown = [i for i in ranking if i not in known]
    if unknown:
        raise FormatError(f"{path}: ranking names unknown ids: {', '.join(unknown)}")
    repeated = sorted({i for i in ranking if ranking.count(i) > 1})
    if repeated:
        raise FormatError(f"{path}: ranking repeats ids: {', '.join(repeated)}")
    return ranking


def _grouped(groups, path: Path) -> list[Paper]:
    papers = []
    for group in groups:
        if "id" not in group:
            raise FormatError(f"{path}: every group needs an 'id'")
        papers.extend(_numbered(group.get("papers") or [], group=str(group["id"]), path=path))
    return papers


def _numbered(entries, *, group: str, path: Path) -> list[Paper]:
    return [_paper(entry, group, number, path) for number, entry in enumerate(entries, start=1)]


def _paper(entry: dict, group: str, number: int, path: Path) -> Paper:
    fallback_name = f"#{number} in {group or 'list'}"
    where = f"{path}: paper {entry.get('id', fallback_name)}"
    for required in ("id", "title"):
        if not entry.get(required):
            raise FormatError(f"{where}: missing '{required}'")

    tags = frozenset(str(t) for t in entry.get("tags") or ())
    if entry.get("core"):
        tags |= {"core"}

    return Paper(
        id=str(entry["id"]),
        title=str(entry["title"]),
        group=group,
        number=number,
        authors=tuple(str(a) for a in entry.get("authors") or ()),
        year=int(entry["year"]) if entry.get("year") else None,
        venue=str(entry.get("venue") or ""),
        kind=str(entry.get("kind") or "paper"),
        tags=tags,
        pdf=str(entry.get("pdf") or ""),
        arxiv=_arxiv_id(entry.get("arxiv"), where),
        doi=str(entry.get("doi") or ""),
        landing=str(entry.get("landing") or ""),
        why=" ".join(str(entry.get("why") or entry.get("read_for") or "").split()),
        open_copy=bool(entry.get("open_copy", True)),
    )


def _arxiv_id(value, where: str) -> str:
    """YAML reads 2010.08440 as the float 2010.0844, silently dropping a digit."""
    if value is None or value == "":
        return ""
    elif isinstance(value, str):
        return value.strip()
    else:
        raise FormatError(f"{where}: quote the arXiv id (\"{value}\"), or YAML mangles it")
