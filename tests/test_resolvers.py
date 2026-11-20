import json

import pytest

from conftest import FakeHttp, arxiv_feed
from readlist import resolvers
from readlist.config import Config
from readlist.model import Paper

API = "https://export.arxiv.org/api/query"
S2 = "https://api.semanticscholar.org/graph/v1/paper/"


def test_explicit_pdf_wins_without_network():
    http = FakeHttp()
    found = resolvers.resolve(Paper(id="p", title="T", pdf="https://x/p.pdf"), http, Config())
    assert found.url == "https://x/p.pdf" and not found.discovered
    assert http.requests == []


def test_arxiv_id_is_title_checked():
    http = FakeHttp({f"{API}?id_list=2302.13863": arxiv_feed(("2302.13863", "Capstone: A Thing"))})
    found = resolvers.resolve(Paper(id="p", title="Capstone: a thing", arxiv="2302.13863"),
                              http, Config())
    assert found.url == "https://arxiv.org/pdf/2302.13863"


def test_wrong_arxiv_id_is_an_error_not_a_download():
    http = FakeHttp({f"{API}?id_list=1111.11111": arxiv_feed(("1111.11111", "Something Else"))})
    with pytest.raises(resolvers.ResolveError, match="Something Else"):
        resolvers.resolve(Paper(id="p", title="Capstone", arxiv="1111.11111"), http, Config())


def test_semantic_scholar_ignores_doi_links_but_uses_arxiv_copy():
    record = {"title": "Paper Title", "openAccessPdf": {"url": "https://doi.org/10.1/x"},
              "externalIds": {"ArXiv": "2401.00001"}}
    http = FakeHttp({S2: json.dumps(record).encode()})
    found = resolvers.resolve(Paper(id="p", title="Paper Title", doi="10.1/x"), http, Config())
    assert found.url == "https://arxiv.org/pdf/2401.00001" and found.discovered


def test_unpaywall_needs_email_and_uses_best_location():
    record = {"best_oa_location": {"url_for_pdf": "https://repo/p.pdf", "host_type": "repository"}}
    http = FakeHttp({"https://api.unpaywall.org/v2/": json.dumps(record).encode(),
                     f"{API}?search_query=": arxiv_feed()})
    paper = Paper(id="p", title="T", doi="10.1/x")

    assert resolvers.resolve(paper, http, Config(email="me@example.org")).url == "https://repo/p.pdf"
    http.requests.clear()
    resolvers.resolve(paper, http, Config())
    assert not any("unpaywall" in url for url in http.requests)


def test_rate_limited_semantic_scholar_falls_through_to_arxiv_search():
    http = FakeHttp({S2: 429, f"{API}?search_query=": arxiv_feed(("2402.2", "My Paper"))})
    found = resolvers.resolve(Paper(id="p", title="My Paper"), http, Config())
    assert found.source == "arxiv search: 2402.2"


def test_open_copy_false_skips_lookups():
    http = FakeHttp()
    assert resolvers.resolve(Paper(id="p", title="T", open_copy=False), http, Config()) is None
    assert http.requests == []


def test_talks_download_only_their_explicit_slides():
    http = FakeHttp()
    slides = Paper(id="p", title="T", kind="talk", pdf="https://x/slides.pdf")
    assert resolvers.resolve(slides, http, Config()).url == "https://x/slides.pdf"
    assert resolvers.resolve(Paper(id="q", title="T", kind="talk"), http, Config()) is None
    assert http.requests == []
