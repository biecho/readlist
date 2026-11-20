"""Fuzzy title comparison, used to verify that a lookup found the right paper."""

from __future__ import annotations

import difflib
import re

MATCH_THRESHOLD = 0.8


def titles_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio() >= MATCH_THRESHOLD


def normalize(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", title).lower().split())
