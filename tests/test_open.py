from pathlib import Path

import pytest

from conftest import PDF
from readlist import cli, opener, readers
from readlist.model import SelectionError

LIST = """
ranking:
  Map: [b, a]
  Later: [c]
groups:
  - id: g
    papers:
      - {id: a, title: A, pdf: "https://x/a.pdf"}
      - {id: b, title: B, landing: "https://landing/b"}
      - {id: c, title: C}
"""


@pytest.fixture
def listing(tmp_path) -> Path:
    path = tmp_path / "list.yaml"
    path.write_text(LIST)
    return path


def test_pick_by_number_range_and_id(listing):
    reading_list = readers.read(listing)
    assert reading_list.positions() == {"b": 1, "a": 2, "c": 3}
    assert [p.id for p in reading_list.pick(["2", "c"])] == ["a", "c"]
    assert [p.id for p in reading_list.pick(["1-2", "a"])] == ["b", "a"]
    with pytest.raises(SelectionError, match="positions run 1-3"):
        reading_list.pick(["7"])
    with pytest.raises(SelectionError, match="neither"):
        reading_list.pick(["nope"])


def test_section_selection_is_case_insensitive(listing):
    assert [p.id for p in readers.read(listing).select(section="map").papers] == ["a", "b"]
    with pytest.raises(SelectionError, match="sections: Map, Later"):
        readers.read(listing).select(section="nope")


def test_open_section_opens_pdfs_in_app_and_placeholders_in_browser(listing, monkeypatch, capsys):
    papers = listing.parent / "papers" / "g"
    papers.mkdir(parents=True)
    (papers / "a.pdf").write_bytes(PDF)
    (papers / "b.url").write_text("[InternetShortcut]\nURL=https://landing/b\n")

    opened, browsed = [], []
    monkeypatch.setattr(opener, "open_pdf", lambda path, app="": opened.append((path.name, app)))
    monkeypatch.setattr(opener, "open_url", browsed.append)

    assert cli.main(["open", str(listing), "--section", "Map", "--app", "PDF Expert"]) == 0
    assert opened == [("a.pdf", "PDF Expert")]
    assert browsed == ["https://landing/b"]
    assert "fetch by hand" in capsys.readouterr().out


def test_open_reports_unfetched_papers(listing, monkeypatch):
    monkeypatch.setattr(opener, "open_pdf", lambda *a, **k: None)
    assert cli.main(["open", str(listing), "3"]) == 1


def test_open_pdf_builds_macos_command(monkeypatch):
    commands = []
    monkeypatch.setattr(opener.sys, "platform", "darwin")
    opener.open_pdf(Path("/p/a.pdf"), "PDF Expert", run=commands.append)
    assert commands == [["open", "-a", "PDF Expert", "/p/a.pdf"]]
