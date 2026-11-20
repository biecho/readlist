"""Terminal output for `readlist rank` and `readlist list`.

    MAP
      1  SoK: Understanding Design Choices and Pitfalls of Trusted Execution
         Environments
         Li et al. · AsiaCCS 2024 · core · fetch by hand
         Design space of TEEs, mapped to the attack class each choice invites.

Color only on a terminal, and never when NO_COLOR is set.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

from readlist.library import Library
from readlist.model import Paper

MAX_WIDTH = 100
STATUS_WORDS = {"have": "downloaded", "manual": "fetch by hand", "missing": "not fetched"}


def entries(
    sections: list[tuple[str, list[tuple[int, Paper]]]],
    library: Library,
    style: Style,
    width: int,
) -> str:
    """Numbered papers under section headings. Numbers come from the caller."""
    number_width = max((len(str(n)) for _, items in sections for n, _ in items), default=1)
    indent = " " * (2 + number_width + 2)

    blocks = []
    for title, items in sections:
        if title:
            blocks.append(style.heading(title.upper()))
        for number, paper in items:
            blocks.append(_entry(number, paper, library, style, width, number_width, indent))
    return "\n\n".join(blocks)


def summary(papers: list[Paper], library: Library, style: Style) -> str:
    counts = {status: 0 for status in STATUS_WORDS}
    for paper in papers:
        counts[library.status(paper)] += 1

    parts = [f"{len(papers)} papers", style.green(f"{counts['have']} downloaded")]
    if counts["manual"]:
        parts.append(style.yellow(f"{counts['manual']} to fetch by hand") +
                     style.dim(f" (open the .url files in {_display_path(library.root)})"))
    if counts["missing"]:
        parts.append(style.red(f"{counts['missing']} not fetched") +
                     style.dim(" (run readlist fetch)"))
    return " · ".join(parts)


def terminal_width() -> int:
    return min(shutil.get_terminal_size((MAX_WIDTH, 24)).columns, MAX_WIDTH)


@dataclass(frozen=True)
class Style:
    color: bool

    @classmethod
    def for_stdout(cls) -> Style:
        return cls(color=sys.stdout.isatty() and "NO_COLOR" not in os.environ)

    def heading(self, text: str) -> str:
        return self._wrap(text, "1;36")

    def bold(self, text: str) -> str:
        return self._wrap(text, "1")

    def dim(self, text: str) -> str:
        return self._wrap(text, "2")

    def green(self, text: str) -> str:
        return self._wrap(text, "32")

    def yellow(self, text: str) -> str:
        return self._wrap(text, "33")

    def red(self, text: str) -> str:
        return self._wrap(text, "31")

    def cyan(self, text: str) -> str:
        return self._wrap(text, "36")

    def _wrap(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text


def _entry(number, paper, library, style, width, number_width, indent) -> str:
    text_width = max(width - len(indent), 30)
    title_lines = textwrap.wrap(paper.title, text_width) or [paper.id]

    lines = [f"  {style.dim(str(number).rjust(number_width))}  {style.bold(title_lines[0])}"]
    lines += [indent + style.bold(line) for line in title_lines[1:]]
    lines.append(indent + _meta(paper, library, style))
    lines += [indent + line for line in textwrap.wrap(paper.why, text_width)]
    return "\n".join(lines)


def _meta(paper: Paper, library: Library, style: Style) -> str:
    parts = []
    authors = short_authors(paper.authors)
    if authors:
        parts.append(authors)
    venue = " ".join(part for part in (paper.venue, str(paper.year or "")) if part)
    if venue:
        parts.append(venue)
    if paper.kind != "paper":
        parts.append(paper.kind)

    rendered = [style.dim(part) for part in parts]
    if "core" in paper.tags:
        rendered.append(style.cyan("core"))
    rendered.append(_status(library.status(paper), style))
    return style.dim(" · ").join(rendered)


def _status(status: str, style: Style) -> str:
    word = STATUS_WORDS[status]
    if status == "have":
        return style.green(word)
    elif status == "manual":
        return style.yellow(word)
    elif status == "missing":
        return style.red(word)
    else:
        raise AssertionError(f"unknown status {status}")


def short_authors(authors: tuple[str, ...]) -> str:
    """'Li et al.', 'Costan & Devadas', 'Van Bulck'."""
    names = [a for a in authors if a.strip().lower() not in ("et al.", "et al", "others")]
    truncated = len(names) < len(authors)
    surnames = [_surname(name) for name in names]

    if not surnames:
        return ""
    elif len(surnames) == 1 and not truncated:
        return surnames[0]
    elif len(surnames) == 2 and not truncated:
        return f"{surnames[0]} & {surnames[1]}"
    else:
        return f"{surnames[0]} et al."


def _surname(name: str) -> str:
    """'Costan, Victor' -> 'Costan'; 'Jo Van Bulck' -> 'Van Bulck'; 'AMD' -> 'AMD'."""
    if "," in name:
        return name.split(",", 1)[0].strip()
    words = name.split()
    particles = {"van", "von", "de", "der", "den", "du", "da", "di", "la", "le"}
    start = len(words) - 1
    while start > 0 and words[start - 1].lower() in particles:
        start -= 1
    return " ".join(words[start:])


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd())) + "/"
    except ValueError:
        return str(path).replace(str(Path.home()), "~", 1) + "/"
