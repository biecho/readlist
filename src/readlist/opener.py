"""Open papers: PDFs in your PDF app, link placeholders in your browser."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Callable

Run = Callable[[list[str]], None]


def open_pdf(path: Path, app: str = "", run: Run | None = None) -> None:
    """Open with `app` (e.g. "PDF Expert"), or the system default for PDFs."""
    run = run or _run
    if sys.platform == "darwin":
        run(["open", *(["-a", app] if app else []), str(path)])
    elif sys.platform.startswith("linux"):
        run([app or "xdg-open", str(path)])
    elif sys.platform == "win32" and not app:
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "win32":
        run([app, str(path)])
    else:
        raise OSError(f"don't know how to open files on {sys.platform}")


def open_url(url: str) -> None:
    webbrowser.open(url)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
