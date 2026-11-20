"""Unpaywall: the best open copy of a published paper, by DOI.

Unpaywall requires a contact email on every request; it is read from the
user's config, never from the list. Without one, this resolver is skipped.
"""

from __future__ import annotations

import urllib.parse

from readlist.config import Config
from readlist.http import Fetcher, HttpError
from readlist.model import Paper
from readlist.resolvers.base import Resolution

API = "https://api.unpaywall.org/v2/"


def resolve(paper: Paper, http: Fetcher, config: Config) -> Resolution | None:
    if not paper.doi or not config.email:
        return None

    url = f"{API}{urllib.parse.quote(paper.doi)}?email={urllib.parse.quote(config.email)}"
    try:
        record = http.get_json(url)
    except HttpError as problem:
        if problem.status == 404:
            return None
        raise

    for location in _locations(record):
        pdf = location.get("url_for_pdf")
        if pdf:
            return Resolution(url=pdf, source=f"unpaywall ({location.get('host_type', '?')})",
                              discovered=True)
    return None


def _locations(record: dict) -> list[dict]:
    best = record.get("best_oa_location")
    others = record.get("oa_locations") or []
    return ([best] if best else []) + [loc for loc in others if loc is not best]
