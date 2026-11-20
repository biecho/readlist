"""The folder of PDFs: <root>/<group>/<id>.pdf.

Looking never changes anything: `state()` only reads. `sync()` (run by
`readlist fetch`) moves PDFs whose paper moved to another group and removes
placeholders a PDF has replaced.

Annotations are never lost. Every download is checksummed into
<root>/.readlist-manifest.json, keyed by paper id. A file that no longer
matches its checksum has been edited (highlights, comments); before it would
be replaced, it is moved to <root>/annotated-backup/.

Papers without an open copy get an <id>.url placeholder, an Internet Shortcut
that opens with a double-click on macOS, Windows and most Linux desktops.
"""

from __future__ import annotations

import enum
import hashlib
import json
import shutil
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from readlist.model import Paper

MANIFEST_NAME = ".readlist-manifest.json"
BACKUP_DIR_NAME = "annotated-backup"
MIN_PDF_BYTES = 10_000  # anything smaller is an error page, not a paper


class Availability(enum.Enum):
    DOWNLOADED = "downloaded"
    FETCH_BY_HAND = "fetch by hand"  # a .url placeholder points at the paper
    LINK = "link"  # a talk or web page: there is only a link
    NOT_FETCHED = "not fetched"

    @property
    def label(self) -> str:
        return self.value


@dataclass(frozen=True)
class State:
    availability: Availability
    path: Path | None = None  # the PDF, when downloaded
    link: str = ""  # where to look, when there is no PDF


class NotAPdf(ValueError):
    pass


class Library:
    def __init__(self, root: Path):
        self.root = root
        self._manifest_path = root / MANIFEST_NAME
        self._manifest = self._load_manifest()

    def state(self, paper: Paper) -> State:
        """Where the paper stands. Reads only."""
        pdf = self._existing_pdf(paper)
        if pdf is not None:
            return State(Availability.DOWNLOADED, path=pdf)
        elif paper.link_only:
            return State(Availability.LINK, link=paper.landing)
        elif self.placeholder_path(paper).exists():
            return State(Availability.FETCH_BY_HAND, link=self._placeholder_target(paper))
        else:
            return State(Availability.NOT_FETCHED)

    def pdf_path(self, paper: Paper) -> Path:
        return self._folder(paper) / f"{paper.id}.pdf"

    def placeholder_path(self, paper: Paper) -> Path:
        return self._folder(paper) / f"{paper.id}.url"

    def sync(self, paper: Paper) -> None:
        """Move the paper's PDF to where the list now puts it; drop an obsolete placeholder."""
        self._relocate(paper)
        if self.pdf_path(paper).exists():
            self.placeholder_path(paper).unlink(missing_ok=True)

    def store(self, paper: Paper, body: bytes, url: str) -> Path | None:
        """Write a downloaded PDF. Returns the backup path if an annotated copy was moved aside."""
        if len(body) < MIN_PDF_BYTES or not body.startswith(b"%PDF"):
            raise NotAPdf(f"not a PDF ({len(body)} bytes)")

        target = self.pdf_path(paper)
        backup = self._preserve_if_annotated(paper, target)

        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".part")
        partial.write_bytes(body)
        partial.replace(target)

        self._manifest[paper.id] = {"path": self._relative(target), "url": url,
                                    "sha256": _sha256(target)}
        self._save_manifest()
        self.placeholder_path(paper).unlink(missing_ok=True)
        return backup

    def write_placeholder(self, paper: Paper, url: str | None = None) -> Path:
        """A double-clickable link to `url`, by default the paper's landing page."""
        target = self.placeholder_path(paper)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"[InternetShortcut]\nURL={url or placeholder_url(paper)}\n")
        return target

    def blocked_link(self, paper: Paper) -> str:
        """The link an existing placeholder holds (e.g. a PDF a site refused to scripts)."""
        return self._placeholder_target(paper) if self.placeholder_path(paper).exists() else ""

    def _existing_pdf(self, paper: Paper) -> Path | None:
        """The PDF where the list puts it, or where it was saved before the paper moved."""
        if self.pdf_path(paper).exists():
            return self.pdf_path(paper)
        record = self._manifest.get(paper.id)
        if record is not None and (self.root / record["path"]).exists():
            return self.root / record["path"]
        return None

    def _placeholder_target(self, paper: Paper) -> str:
        for line in self.placeholder_path(paper).read_text().splitlines():
            if line.startswith("URL="):
                return line[len("URL="):].strip()
        return ""

    def _folder(self, paper: Paper) -> Path:
        return self.root / paper.group if paper.group else self.root

    def _relocate(self, paper: Paper) -> None:
        record = self._manifest.get(paper.id)
        if record is None:
            return
        current = self.root / record["path"]
        target = self.pdf_path(paper)
        if current == target or not current.exists() or target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(current, target)
        record["path"] = self._relative(target)
        self._save_manifest()

    def _preserve_if_annotated(self, paper: Paper, target: Path) -> Path | None:
        if not target.exists():
            return None
        record = self._manifest.get(paper.id)
        if record is not None and _sha256(target) == record["sha256"]:
            return None  # untouched since download: safe to overwrite

        # Edited, or never downloaded by readlist: either way, keep it.
        backup_dir = self.root / BACKUP_DIR_NAME
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{target.stem}-{time.strftime('%Y%m%d-%H%M%S')}.pdf"
        shutil.move(target, backup)
        return backup

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _load_manifest(self) -> dict:
        if self._manifest_path.exists():
            return json.loads(self._manifest_path.read_text())
        return {}

    def _save_manifest(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(json.dumps(self._manifest, indent=2, sort_keys=True) + "\n")


def placeholder_url(paper: Paper) -> str:
    """Where a human should look: the landing page, else a DOI, else a Scholar search."""
    if paper.landing:
        return paper.landing
    elif paper.doi:
        return f"https://doi.org/{paper.doi}"
    else:
        return "https://scholar.google.com/scholar?q=" + urllib.parse.quote(f'"{paper.title}"')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
