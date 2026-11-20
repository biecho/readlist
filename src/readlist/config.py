"""Per-user settings. Never stored in a reading list, so lists stay shareable.

~/.config/readlist/config.toml (or $XDG_CONFIG_HOME/readlist/config.toml):

    email = "you@example.org"          # Unpaywall requires a contact email
    semantic_scholar_key = "..."       # optional private Semantic Scholar quota

Environment variables READLIST_EMAIL and S2_API_KEY override the file.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    email: str = ""
    semantic_scholar_key: str = ""


def load(env: Mapping[str, str] | None = None) -> Config:
    if env is None:
        env = os.environ
    stored = _read_file(config_path(env))
    return Config(
        email=env.get("READLIST_EMAIL") or str(stored.get("email", "")),
        semantic_scholar_key=env.get("S2_API_KEY") or str(stored.get("semantic_scholar_key", "")),
    )


def config_path(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "readlist" / "config.toml"


def _read_file(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)
