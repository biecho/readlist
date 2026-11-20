"""YAML reading lists.

Either grouped:

    groups:            # `stages:` is accepted as an alias
      - id: 01-basics
        title: Start here
        papers:
          - id: costan2016sgx
            title: Intel SGX Explained
            pdf: https://...

or flat, with a top-level `papers:` list. Unknown keys (reading notes, say)
are ignored.

An optional top-level `ranking:` lists paper ids from read-first to
read-last, across groups; it sets the reading order `readlist ls` shows. Either a plain list of
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
        raise FormatError(_yaml_error(path, problem)) from problem
    if not isinstance(data, dict):
        raise FormatError(f"{path}: top level must be a mapping")

    groups = data.get("groups", data.get("stages"))
    if groups is not None:
        papers = _grouped(groups, path)
    elif "papers" in data:
        papers = _papers(data["papers"], group="", path=path)
    else:
        raise FormatError(f"{path}: needs a top-level 'groups' (or 'stages') or 'papers' list")

    titles = {str(g["id"]): str(g.get("title") or "") for g in groups or ()}
    ranking = _ranking(data.get("ranking"), path)
    return ReadingList(source=path, papers=tuple(papers), ranking=ranking, group_titles=titles)


def _ranking(entries, path: Path) -> tuple[Section, ...]:
    """The top-level `ranking:`. Unknown or repeated ids are left for `readlist check`."""
    if entries is None:
        return ()
    elif isinstance(entries, dict):
        return tuple(Section(str(title), _ids(ids, path)) for title, ids in entries.items())
    elif isinstance(entries, list):
        return (Section("", _ids(entries, path)),)
    else:
        raise FormatError(f"{path}: ranking must be a list of ids or a mapping of sections")


def _yaml_error(path: Path, problem: yaml.YAMLError) -> str:
    """One line, with the line number: 'list.yaml:25: mapping values are not allowed here'."""
    mark = getattr(problem, "problem_mark", None)
    where = f"{path}:{mark.line + 1}" if mark is not None else str(path)
    reason = getattr(problem, "problem", None) or "invalid YAML"
    return f"{where}: {reason}"


def _ids(entries, path: Path) -> tuple[str, ...]:
    if not isinstance(entries, list):
        raise FormatError(f"{path}: each ranking section must be a list of ids")
    return tuple(str(entry) for entry in entries)


def _grouped(groups, path: Path) -> list[Paper]:
    papers = []
    for group in groups:
        if "id" not in group:
            raise FormatError(f"{path}: every group needs an 'id'")
        papers.extend(_papers(group.get("papers") or [], group=str(group["id"]), path=path))
    return papers


def _papers(entries, *, group: str, path: Path) -> list[Paper]:
    return [_paper(entry, group, position, path) for position, entry in enumerate(entries, start=1)]


def _paper(entry: dict, group: str, position: int, path: Path) -> Paper:
    fallback_name = f"#{position} in {group or 'list'}"
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
