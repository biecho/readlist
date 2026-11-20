"""BibTeX reading lists.

Fields used per entry:
  title, author, year, booktitle/journal
  pdfurl     direct link to an open copy (non-standard; BibTeX styles ignore it)
  url        used as `pdf` when it ends in .pdf, otherwise as the landing page
  eprint     arXiv id (with archivePrefix = arXiv, or when it looks like one)
  doi
  opencopy   `none` marks an entry whose only open copy is another version
             (e.g. a superseded preprint): only an explicit pdfurl counts
  group      optional folder name

An entry whose only source is a non-PDF `url` is a web resource (a spec, a
repository) and gets a link placeholder rather than a download.

With a .bbl file, only cited entries are kept, and the citation order becomes
the reading order, so numbers match the paper's.
"""

from __future__ import annotations

import re
from pathlib import Path

from readlist.model import ARXIV_ID, FormatError, Paper, ReadingList, Section

ENTRY_START = re.compile(r"@\s*(\w+)\s*\{", re.ASCII)
SKIPPED_TYPES = {"comment", "string", "preamble"}
BIBITEM = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


def read_bibtex(path: Path, *, bbl: Path | None = None) -> ReadingList:
    entries = parse_bibtex(path.read_text())
    papers = {key: _paper(key, fields) for key, fields in entries}

    if bbl is None:
        return ReadingList(source=path, papers=tuple(papers.values()))

    cited = list(dict.fromkeys(cited_keys(bbl.read_text())))
    missing = [key for key in cited if key not in papers]
    if missing:
        raise FormatError(f"{bbl}: cites keys not in {path.name}: {', '.join(missing)}")
    return ReadingList(source=path, papers=tuple(papers[key] for key in cited),
                       ranking=(Section("", tuple(cited)),))


def parse_bibtex(text: str) -> list[tuple[str, dict[str, str]]]:
    """Return (key, fields) per entry, field names lower-cased, values cleaned."""
    entries = []
    position = 0
    while True:
        match = ENTRY_START.search(text, position)
        if match is None:
            return entries

        entry_type = match.group(1).lower()
        body, position = _balanced(text, match.end() - 1)
        if entry_type in SKIPPED_TYPES:
            continue

        key, _, rest = body.partition(",")
        entries.append((key.strip(), _fields(rest)))


def cited_keys(bbl_text: str) -> list[str]:
    return [key.strip() for key in BIBITEM.findall(bbl_text)]


def _paper(key: str, fields: dict[str, str]) -> Paper:
    if not fields.get("title"):
        raise FormatError(f"bib entry {key}: missing title")

    url = fields.get("url", "")
    pdf = fields.get("pdfurl") or (url if url.lower().endswith(".pdf") else "")
    arxiv = _arxiv(fields)
    doi = fields.get("doi", "")
    landing = url if url and url != pdf else (f"https://doi.org/{doi}" if doi else "")
    is_web_resource = bool(url) and not (pdf or arxiv or doi)

    return Paper(
        id=key,
        title=_strip_braces(fields["title"]),
        group=fields.get("group", ""),
        authors=tuple(a.strip() for a in fields.get("author", "").split(" and ") if a.strip()),
        year=int(fields["year"]) if fields.get("year", "").isdigit() else None,
        venue=fields.get("booktitle") or fields.get("journal") or "",
        kind="web" if is_web_resource else "paper",
        pdf=pdf,
        arxiv=arxiv,
        doi=doi,
        landing=landing,
        open_copy=fields.get("opencopy", "").lower() != "none",
    )


def _arxiv(fields: dict[str, str]) -> str:
    eprint = fields.get("eprint", "").strip()
    if not eprint:
        return ""
    elif fields.get("archiveprefix", "").lower() == "arxiv" or ARXIV_ID.match(eprint):
        return eprint
    else:
        return ""


def _fields(body: str) -> dict[str, str]:
    fields = {}
    position = 0
    while True:
        equals = body.find("=", position)
        if equals == -1:
            return fields
        name = body[position:equals].strip(" \t\r\n,").lower()
        value, position = _value(body, equals + 1)
        if name:
            fields[name] = " ".join(value.split())


def _value(body: str, position: int) -> tuple[str, int]:
    """Read one field value: {braced}, "quoted", or a bare token, joined by #."""
    parts = []
    while True:
        while position < len(body) and body[position].isspace():
            position += 1
        if position >= len(body):
            break

        char = body[position]
        if char == "{":
            inner, position = _balanced(body, position)
            parts.append(inner)
        elif char == '"':
            end = _closing_quote(body, position)
            parts.append(body[position + 1:end])
            position = end + 1
        else:
            end = position
            while end < len(body) and body[end] not in ",#}\n":
                end += 1
            parts.append(body[position:end].strip())
            position = end

        while position < len(body) and body[position].isspace():
            position += 1
        if position < len(body) and body[position] == "#":
            position += 1
            continue
        break

    if position < len(body) and body[position] == ",":
        position += 1
    return "".join(parts), position


def _balanced(text: str, open_brace: int) -> tuple[str, int]:
    """Contents of the brace group starting at text[open_brace], and the index after it."""
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1:index], index + 1
    raise FormatError(f"unbalanced braces near: {text[open_brace:open_brace + 60]!r}")


def _closing_quote(text: str, open_quote: int) -> int:
    depth = 0
    for index in range(open_quote + 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        elif text[index] == '"' and depth == 0:
            return index
    raise FormatError(f"unterminated string near: {text[open_quote:open_quote + 60]!r}")


def _strip_braces(text: str) -> str:
    return text.replace("{", "").replace("}", "")
