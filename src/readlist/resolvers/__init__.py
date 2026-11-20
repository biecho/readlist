"""Find a link to an open copy of a paper.

Resolvers are tried in order; the first that returns a Resolution wins.
A resolver returns None when it has nothing to offer, and raises
ResolveError when the list itself is wrong (e.g. an arXiv id that belongs
to a different paper), so a mistake is reported instead of hidden.
"""

from __future__ import annotations

from typing import Callable

from readlist.config import Config
from readlist.http import Fetcher
from readlist.model import Paper
from readlist.resolvers import arxiv, explicit, semantic_scholar, unpaywall
from readlist.resolvers.base import Resolution, ResolveError

__all__ = ["Resolution", "ResolveError", "chain", "resolve"]

Resolver = Callable[[Paper, Fetcher, Config], "Resolution | None"]


def resolve(paper: Paper, http: Fetcher, config: Config) -> Resolution | None:
    for resolver in chain():
        # open_copy: false means lookups would find another version (e.g. a preprint).
        if not (paper.searchable and paper.open_copy) and resolver is not explicit.resolve:
            continue
        resolution = resolver(paper, http, config)
        if resolution is not None:
            return resolution
    return None


def chain() -> tuple[Resolver, ...]:
    return (
        explicit.resolve,
        arxiv.resolve_id,
        unpaywall.resolve,
        semantic_scholar.resolve,
        arxiv.resolve_search,
    )
