from pathlib import Path

import pytest

from conftest import PDF
from readlist import commands, opener
from readlist.commands import Opened
from readlist.library import Library
from readlist.model import Paper, ReadingList, SelectionError, Section


def make_list(tmp_path) -> tuple[ReadingList, Library]:
    papers = (
        Paper(id="a", title="A", group="g"),
        Paper(id="b", title="B", group="g", landing="https://landing/b"),
        Paper(id="c", title="C", group="g"),
        Paper(id="t", title="Talk", group="g", kind="talk", landing="https://talk"),
    )
    folder = tmp_path / "papers" / "g"
    folder.mkdir(parents=True)
    (folder / "a.pdf").write_bytes(PDF)
    (folder / "b.url").write_text("[InternetShortcut]\nURL=https://landing/b\n")
    reading_list = ReadingList(source=tmp_path / "l.yaml", papers=papers,
                               ranking=(Section("", ("t", "b", "a", "c")),))
    return reading_list, Library(tmp_path / "papers")


def test_open_dispatches_on_availability(tmp_path):
    reading_list, library = make_list(tmp_path)
    pdfs, urls = [], []
    results = commands.open_entries(reading_list.entries(), library, pdfs.append, urls.append)

    assert [(r.entry.number, r.opened) for r in results] == [
        (1, Opened.LINK), (2, Opened.FETCH_BY_HAND), (3, Opened.PDF), (4, Opened.NOT_FETCHED)]
    assert [p.name for p in pdfs] == ["a.pdf"]
    assert urls == ["https://talk", "https://landing/b"]


def test_opening_many_by_filter_needs_all(tmp_path):
    reading_list, _ = make_list(tmp_path)
    many = reading_list.entries() * 3
    with pytest.raises(SelectionError, match="add --all"):
        commands.check_open_count(many, picked=False, allow_many=False)
    commands.check_open_count(many, picked=True, allow_many=False)
    commands.check_open_count(many, picked=False, allow_many=True)


def test_open_pdf_builds_macos_command(monkeypatch):
    commands_run = []
    monkeypatch.setattr(opener.sys, "platform", "darwin")
    opener.open_pdf(Path("/p/a.pdf"), "PDF Expert", run=commands_run.append)
    assert commands_run == [["open", "-a", "PDF Expert", "/p/a.pdf"]]
