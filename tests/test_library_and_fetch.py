from dataclasses import replace
from pathlib import Path

from conftest import PDF, FakeHttp
from readlist import commands, writeback
from readlist.commands import FetchOptions, Result
from readlist.config import Config
from readlist.library import Availability, Library
from readlist.model import Paper, ReadingList

PAPER = Paper(id="p", title="T", group="g", pdf="https://x/p.pdf")


def fetch(tmp_path, papers, http, options=FetchOptions()):
    reading_list = ReadingList(source=tmp_path / "list.yaml", papers=tuple(papers))
    return commands.fetch(reading_list.entries(), Library(tmp_path / "papers"), http, Config(),
                          options)


def results(outcomes):
    return [o.result for o in outcomes]


def test_download_then_have(tmp_path):
    http = FakeHttp({"https://x/p.pdf": PDF})
    assert results(fetch(tmp_path, [PAPER], http)) == [Result.GOT]
    assert (tmp_path / "papers/g/p.pdf").read_bytes() == PDF
    assert results(fetch(tmp_path, [PAPER], http)) == [Result.HAVE]
    assert len(http.requests) == 1


def test_html_error_page_is_rejected(tmp_path):
    [outcome] = fetch(tmp_path, [PAPER], FakeHttp({"https://x/p.pdf": b"<html>bot check</html>"}))
    assert outcome.result is Result.FAILED and "not a PDF" in outcome.detail
    assert not (tmp_path / "papers/g/p.pdf").exists()


def test_force_preserves_annotated_copy(tmp_path):
    http = FakeHttp({"https://x/p.pdf": PDF})
    fetch(tmp_path, [PAPER], http)
    target = tmp_path / "papers/g/p.pdf"
    target.write_bytes(PDF + b"highlights")

    [outcome] = fetch(tmp_path, [PAPER], http, FetchOptions(force=True))
    backups = list((tmp_path / "papers/annotated-backup").glob("*.pdf"))
    assert outcome.result is Result.GOT and len(backups) == 1
    assert backups[0].read_bytes().endswith(b"highlights")
    assert target.read_bytes() == PDF


def test_looking_never_moves_files_but_fetch_does(tmp_path):
    fetch(tmp_path, [PAPER], FakeHttp({"https://x/p.pdf": PDF}))
    moved = replace(PAPER, group="h")
    library = Library(tmp_path / "papers")

    state = library.state(moved)
    assert state.availability is Availability.DOWNLOADED
    assert state.path == tmp_path / "papers/g/p.pdf"  # found where it was, not moved

    assert results(fetch(tmp_path, [moved], FakeHttp())) == [Result.HAVE]
    assert (tmp_path / "papers/h/p.pdf").exists() and not (tmp_path / "papers/g/p.pdf").exists()


def test_dry_run_changes_nothing(tmp_path):
    paper = replace(PAPER, pdf="", landing="https://landing", open_copy=False)
    [outcome] = fetch(tmp_path, [paper], FakeHttp(), FetchOptions(dry_run=True))
    assert outcome.result is Result.FETCH_BY_HAND
    assert not (tmp_path / "papers").exists()


def test_no_open_copy_writes_placeholder_then_pdf_replaces_it(tmp_path):
    paper = replace(PAPER, pdf="", landing="https://landing", open_copy=False)
    [outcome] = fetch(tmp_path, [paper], FakeHttp())
    placeholder = tmp_path / "papers/g/p.url"
    assert outcome.result is Result.FETCH_BY_HAND
    assert "URL=https://landing" in placeholder.read_text()
    assert Library(tmp_path / "papers").state(paper).link == "https://landing"

    fetch(tmp_path, [PAPER], FakeHttp({"https://x/p.pdf": PDF}))
    assert not placeholder.exists()


def test_talk_without_slides_is_a_link(tmp_path):
    talk = Paper(id="t", title="Talk", kind="talk", landing="https://talk")
    [outcome] = fetch(tmp_path, [talk], FakeHttp())
    assert outcome.result is Result.LINK
    assert Library(tmp_path / "papers").state(talk).availability is Availability.LINK


def test_record_writes_discovered_link_into_yaml(tmp_path):
    listing = tmp_path / "list.yaml"
    listing.write_text("papers:\n  - id: p  # keep me\n    title: My Paper\n    year: 2024\n")
    feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            b"<id>http://arxiv.org/abs/2402.00002v1</id><title>My Paper</title></entry></feed>")
    http = FakeHttp({"https://export.arxiv.org/": feed, "https://arxiv.org/pdf/": PDF})

    [outcome] = fetch(tmp_path, [Paper(id="p", title="My Paper")], http,
                      FetchOptions(record_into=listing))
    assert outcome.result is Result.GOT and "recorded in list.yaml" in outcome.detail
    assert listing.read_text() == ("papers:\n  - id: p  # keep me\n    title: My Paper\n"
                                   "    pdf: https://arxiv.org/pdf/2402.00002\n    year: 2024\n")


def test_writeback_bibtex_and_csv(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@misc{k,\n  title = {T}}\n")
    writeback.record_pdf_link(bib, "k", "https://x/k.pdf")
    assert bib.read_text() == "@misc{k,\n  pdfurl = {https://x/k.pdf},\n  title = {T}}\n"

    table = tmp_path / "list.csv"
    table.write_text("id,title\nk,T\n")
    writeback.record_pdf_link(table, "k", "https://x/k.pdf")
    assert table.read_text() == "id,title,pdf\nk,T,https://x/k.pdf\n"


def test_check_flags_fields_duplicates_and_ranking(tmp_path):
    from readlist.model import Section
    papers = (Paper(id="a", title="T", arxiv="12.3"), Paper(id="a", title="U", doi="nope"))
    reading_list = ReadingList(source=Path("l.yaml"), papers=papers,
                               ranking=(Section("", ("zz",)),))
    problems = commands.check(reading_list)
    assert "a: duplicate id" in problems
    assert "ranking names unknown id 'zz'" in problems
    assert any("not an arXiv id" in p for p in problems)
    assert any("not a DOI" in p for p in problems)


def test_blocked_discovered_link_becomes_placeholder_but_blocked_list_link_fails(tmp_path):
    discovered = replace(PAPER, pdf="", doi="10.1/x")
    record = b'{"title": "T", "openAccessPdf": {"url": "https://dl.acm.org/doi/pdf/10.1/x"}}'
    http = FakeHttp({"https://api.semanticscholar.org/": record, "https://dl.acm.org/": 403})
    [outcome] = fetch(tmp_path, [discovered], http)
    assert outcome.result is Result.FETCH_BY_HAND
    assert "URL=https://dl.acm.org/doi/pdf/10.1/x" in (tmp_path / "papers/g/p.url").read_text()

    [outcome] = fetch(tmp_path, [replace(PAPER, pdf="https://dl.acm.org/x.pdf")], http)
    assert outcome.result is Result.FAILED
