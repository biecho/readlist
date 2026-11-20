"""Record a discovered PDF link in the list file, so the next run (and every
collaborator) gets it without a lookup.

Edits are textual and minimal: comments, ordering and formatting survive.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path


class WritebackError(ValueError):
    pass


def record_pdf_link(list_path: Path, paper_id: str, url: str) -> None:
    suffix = list_path.suffix.lower()
    text = list_path.read_text()

    if suffix in (".yaml", ".yml"):
        updated = _yaml(text, paper_id, url)
    elif suffix == ".bib":
        updated = _bibtex(text, paper_id, url)
    elif suffix == ".csv":
        updated = _csv(text, paper_id, url)
    else:
        raise WritebackError(f"{list_path}: cannot record links in '{suffix}' files")

    list_path.write_text(updated)


def _yaml(text: str, paper_id: str, url: str) -> str:
    lines = text.splitlines(keepends=True)
    start = _yaml_entry_line(lines, paper_id)
    dash_indent = len(lines[start]) - len(lines[start].lstrip())
    key_indent = " " * (dash_indent + 2)

    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and len(line) - len(line.lstrip()) <= dash_indent:
            break
        end += 1

    block = lines[start:end]
    if any(line.startswith(f"{key_indent}pdf:") for line in block):
        raise WritebackError(f"{paper_id}: already has a pdf link")

    insert_at = start + 1
    for offset, line in enumerate(block[1:], start=1):
        if line.startswith(f"{key_indent}title:") and not line.rstrip().endswith(("|", ">")):
            insert_at = start + offset + 1
            break

    if not lines[insert_at - 1].endswith("\n"):
        lines[insert_at - 1] += "\n"
    lines.insert(insert_at, f"{key_indent}pdf: {url}\n")
    return "".join(lines)


def _yaml_entry_line(lines: list[str], paper_id: str) -> int:
    pattern = re.compile(rf"^\s*-\s+id:\s*['\"]?{re.escape(paper_id)}['\"]?\s*(#.*)?$")
    matches = [i for i, line in enumerate(lines) if pattern.match(line.rstrip("\n"))]
    if len(matches) == 1:
        return matches[0]
    elif not matches:
        raise WritebackError(f"{paper_id}: no '- id: {paper_id}' line found")
    else:
        raise WritebackError(f"{paper_id}: appears {len(matches)} times")


def _bibtex(text: str, paper_id: str, url: str) -> str:
    pattern = re.compile(rf"@\s*\w+\s*\{{\s*{re.escape(paper_id)}\s*,")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise WritebackError(f"{paper_id}: found {len(matches)} bib entries, expected 1")
    position = matches[0].end()
    return f"{text[:position]}\n  pdfurl = {{{url}}},{text[position:]}"


def _csv(text: str, paper_id: str, url: str) -> str:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise WritebackError("empty CSV")
    columns = list(rows[0].keys())
    key_column = next((c for c in ("id", "citekey", "key") if c in columns), None)
    if key_column is None:
        raise WritebackError("CSV has no id column")

    matching = [row for row in rows if row[key_column].strip() == paper_id]
    if len(matching) != 1:
        raise WritebackError(f"{paper_id}: found {len(matching)} rows, expected 1")
    if "pdf" not in columns:
        columns.append("pdf")
    elif matching[0].get("pdf"):
        raise WritebackError(f"{paper_id}: already has a pdf link")
    matching[0]["pdf"] = url

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
