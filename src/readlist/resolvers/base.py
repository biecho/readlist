"""Types shared by all resolvers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Resolution:
    url: str
    source: str  # human-readable, e.g. "arxiv 2302.13863"
    discovered: bool  # True if found by lookup rather than written in the list


class ResolveError(Exception):
    """The list points at the wrong thing."""
