from readlist import render
from readlist.library import Library
from readlist.model import Paper


def test_short_authors():
    assert render.short_authors(("Jo Van Bulck",)) == "Van Bulck"
    assert render.short_authors(("Costan, Victor", "Devadas, Srinivas")) == "Costan & Devadas"
    assert render.short_authors(("A B", "C D", "E F")) == "B et al."
    assert render.short_authors(("Zhongshu Gu", "et al.")) == "Gu et al."
    assert render.short_authors(()) == ""


def test_entry_shows_title_meta_and_reason_without_color(tmp_path):
    paper = Paper(id="p", title="A Paper", authors=("Ada Lovelace",), venue="CCS", year=2026,
                  tags=frozenset({"core"}), why="Because.")
    text = render.entries([("Map", [(1, paper)])], Library(tmp_path), render.Style(color=False), 80)
    assert text == ("MAP\n\n"
                    "  1  A Paper\n"
                    "     Lovelace · CCS 2026 · core · not fetched\n"
                    "     Because.")
