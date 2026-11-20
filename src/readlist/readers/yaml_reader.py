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
position within their group (shown by `readlist list`). Unknown keys
(reading notes, say) are ignored.

An optional top-level `ranking:` lists paper ids from read-first to
read-last, across groups; `readlist rank` shows it. Either a plain list of
ids, or a mapping from section title to a list of ids:

    ranking:
      Map: [li2024sok, misono2024cvm]
      Frontier: [schluter2024wesee, demeulemeester2025badram]
"""

from __future__ import annotations

from pathlib import Path

import yaml

from readlist.model import FormatError, Paper, ReadingList, Section

def read_yaml(path: Path) -> ReadingList:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as problem:
        raise FormatError(f"{path}: invalid YAML: {problem}") from problem
    if not isinstance(data, dict):
        raise FormatError(f"{path}: top level must be a mapping")

    groups = data.get("groups", data.get("stages"))
    if groups is not None:
        papers = _grouped(groups, path)
    elif "papers" in data:
        papers = _numbered(data["papers"], group="", path=path)
    else:
        raise FormatError(f"{path}: needs a top-level 'groups' (or 'stages') or 'papers' list")

    titles = {str(g["id"]): str(g.get("title") or "") for g in groups or ()}
    ranking = _ranking(data.get("ranking"), papers, path)
    return ReadingList(source=path, papers=tuple(papers), ranking=ranking, group_titles=titles)


def _ranking(entries, papers: list[Paper], path: Path) -> tuple[Section, ...]:
    """The top-level `ranking:`. Every id must exist, and appear once."""
    if entries is None:
        return ()
    elif isinstance(entries, dict):
        sections = tuple(Section(str(title), _ids(ids, path)) for title, ids in entries.items())
    elif isinstance(entries, list):
        sections = (Section("", _ids(entries, path)),)
    else:
        raise FormatError(f"{path}: ranking must be a list of ids or a mapping of sections")

    ranked = [i for section in sections for i in section.ids]
    known = {p.id for p in papers}
    unknown = [i for i in ranked if i not in known]
    if unknown:
        raise FormatError(f"{path}: ranking names unknown ids: {', '.join(unknown)}")
    repeated = sorted({i for i in ranked if ranked.count(i) > 1})
    if repeated:
        raise FormatError(f"{path}: ranking repeats ids: {', '.join(repeated)}")
    return sections


def _ids(entries, path: Path) -> tuple[str, ...]:
    if not isinstance(entries, list):
        raise FormatError(f"{path}: each ranking section must be a list of ids")
    return tuple(str(entry) for entry in entries)


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
