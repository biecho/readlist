"""Semantic Scholar: an open-access PDF or an arXiv copy, by DOI or by title.

Its `openAccessPdf` is often just a DOI link, i.e. a publisher landing page;
those are ignored. Anonymous clients share one quota, so a 429 after retries
means "no answer", not failure. Set S2_API_KEY for a private quota.
"""

from __future__ import annotations

import urllib.parse

from readlist.config import Config
from readlist.http import Fetcher, HttpError
from readlist.model import Paper
from readlist.resolvers.base import Resolution
from readlist.resolvers.arxiv import pdf_url
from readlist.resolvers.titles import titles_match

API = "https://api.semanticscholar.org/graph/v1/paper/"
FIELDS = "title,openAccessPdf,externalIds"
LANDING_HOSTS = {"doi.org", "dx.doi.org"}
NO_ANSWER = {404, 429}


def resolve(paper: Paper, http: Fetcher, config: Config) -> Resolution | None:
    record = _lookup(paper, http, config)
    if record is None or not titles_match(record.get("title"), paper.title):
        return None

    pdf = (record.get("openAccessPdf") or {}).get("url") or ""
    if pdf and urllib.parse.urlsplit(pdf).netloc not in LANDING_HOSTS:
        return Resolution(url=pdf, source="semantic scholar", discovered=True)

    arxiv_id = (record.get("externalIds") or {}).get("ArXiv")
    if arxiv_id:
        return Resolution(url=pdf_url(arxiv_id), source=f"semantic scholar -> arxiv {arxiv_id}",
                          discovered=True)
    return None


def _lookup(paper: Paper, http: Fetcher, config: Config) -> dict | None:
    if paper.doi:
        url = f"{API}DOI:{urllib.parse.quote(paper.doi)}?fields={FIELDS}"
    else:
        url = f"{API}search/match?query={urllib.parse.quote(paper.title)}&fields={FIELDS}"
    headers = {"x-api-key": config.semantic_scholar_key} if config.semantic_scholar_key else None

    try:
        record = http.get_json(url, headers)
    except HttpError as problem:
        if problem.status in NO_ANSWER:
            return None
        raise

    if "data" in record:  # search/match wraps its single best hit
        hits = record["data"]
        return hits[0] if hits else None
    return record
