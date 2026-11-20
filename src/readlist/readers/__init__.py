"""Turn a reading-list file (YAML, BibTeX or CSV) into a ReadingList."""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from readlist.model import FormatError, ReadingList
from readlist.readers.bibtex import read_bibtex
from readlist.readers.table import GROUP_COLUMNS, KEY_COLUMNS, read_csv
from readlist.readers.yaml_reader import read_yaml

UNSORTED = "unsorted"


def read(path: Path, *, bbl: Path | None = None, groups: Path | None = None) -> ReadingList:
    """Read any supported list. `groups` is a CSV that assigns each id a folder."""
    reading_list = _read_by_suffix(path, bbl)
    if groups is not None:
        reading_list = apply_groups(reading_list, groups)
    return reading_list


def apply_groups(reading_list: ReadingList, groups_csv: Path) -> ReadingList:
    """File every paper under the group the CSV gives it; unlisted papers go to 'unsorted'."""
    with groups_csv.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise FormatError(f"{groups_csv}: no rows")

    key_column = _pick_column(rows[0], KEY_COLUMNS, groups_csv)
    group_column = _pick_column(rows[0], GROUP_COLUMNS, groups_csv)
    group_of = {row[key_column].strip(): row[group_column].strip() for row in rows}

    papers = tuple(p.with_group(group_of.get(p.id) or UNSORTED) for p in reading_list.papers)
    return replace(reading_list, papers=papers)


def _read_by_suffix(path: Path, bbl: Path | None) -> ReadingList:
    suffix = path.suffix.lower()
    if bbl is not None and suffix != ".bib":
        raise FormatError("--bbl only applies to a .bib list")

    if suffix in (".yaml", ".yml"):
        return read_yaml(path)
    elif suffix == ".bib":
        return read_bibtex(path, bbl=bbl)
    elif suffix == ".csv":
        return read_csv(path)
    else:
        raise FormatError(f"{path}: unsupported format '{suffix}' (use .yaml, .bib or .csv)")


def _pick_column(row: dict, candidates: tuple[str, ...], path: Path) -> str:
    for name in candidates:
        if name in row:
            return name
    raise FormatError(f"{path}: needs one of the columns {', '.join(candidates)}")
