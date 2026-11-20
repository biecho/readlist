"""A `pdf` link written in the list. A hand-found link always wins."""

from __future__ import annotations

from readlist.config import Config
from readlist.http import Fetcher
from readlist.model import Paper
from readlist.resolvers.base import Resolution


def resolve(paper: Paper, http: Fetcher, config: Config) -> Resolution | None:
    if not paper.pdf:
        return None
    return Resolution(url=paper.pdf, source="pdf link in list", discovered=False)
