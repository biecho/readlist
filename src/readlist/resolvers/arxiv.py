"""arXiv: a given id (title-checked), or a search by title as the last resort."""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET

from readlist.config import Config
from readlist.http import Fetcher
from readlist.model import Paper
from readlist.resolvers.base import Resolution, ResolveError
from readlist.resolvers.titles import normalize, titles_match

API = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
SEARCH_RESULTS = 5
VERSION_SUFFIX = re.compile(r"v\d+$")


def resolve_id(paper: Paper, http: Fetcher, config: Config) -> Resolution | None:
    if not paper.arxiv:
        return None

    found = _entries(http.get_xml(f"{API}?id_list={urllib.parse.quote(paper.arxiv)}"))
    if not found:
        raise ResolveError(f"arXiv id {paper.arxiv} does not exist")

    _, arxiv_title = found[0]
    if titles_match(arxiv_title, paper.title):
        return Resolution(url=pdf_url(paper.arxiv), source=f"arxiv {paper.arxiv}", discovered=False)
    else:
        raise ResolveError(
            f"arXiv id {paper.arxiv} is titled '{arxiv_title}'. If that is this paper "
            f"under another title, set `pdf: {pdf_url(paper.arxiv)}` instead")


def resolve_search(paper: Paper, http: Fetcher, config: Config) -> Resolution | None:
    query = urllib.parse.quote(f'ti:"{normalize(paper.title)}"')
    feed = http.get_xml(f"{API}?search_query={query}&max_results={SEARCH_RESULTS}")
    for arxiv_id, title in _entries(feed):
        if titles_match(title, paper.title):
            return Resolution(url=pdf_url(arxiv_id), source=f"arxiv search: {arxiv_id}",
                              discovered=True)
    return None


def pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}"


def _entries(feed: ET.Element) -> list[tuple[str, str]]:
    """(unversioned id, title) per result, so links follow the latest version.

    arXiv reports a bad id as an entry titled 'Error'.
    """
    entries = []
    for entry in feed.findall("a:entry", ATOM):
        title = " ".join(entry.findtext("a:title", default="", namespaces=ATOM).split())
        entry_id = entry.findtext("a:id", default="", namespaces=ATOM)
        if title and title != "Error" and "/abs/" in entry_id:
            arxiv_id = VERSION_SUFFIX.sub("", entry_id.rsplit("/abs/", 1)[-1])
            entries.append((arxiv_id, title))
    return entries
