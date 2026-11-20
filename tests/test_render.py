from pathlib import Path

from readlist import render
from readlist.commands import Outcome, Result
from readlist.library import Library
from readlist.model import Paper, ReadingList, Section


def test_short_authors():
    assert render.short_authors(("Jo Van Bulck",)) == "Van Bulck"
    assert render.short_authors(("Costan, Victor", "Devadas, Srinivas")) == "Costan & Devadas"
    assert render.short_authors(("A B", "C D", "E F")) == "B et al."
    assert render.short_authors(("Zhongshu Gu", "et al.")) == "Gu et al."
    assert render.short_authors(()) == ""


PAPER = Paper(id="lovelace1843", title="A Paper", authors=("Ada Lovelace",), venue="CCS",
              year=2026, tags=frozenset({"core"}), why="Because.")
LIST = ReadingList(source=Path("l.yaml"), papers=(PAPER,), ranking=(Section("Map", ("lovelace1843",)),))


def test_terminal_view_shows_number_title_meta_id_and_reason(tmp_path):
    text = render.terminal(LIST.entries(), Library(tmp_path), render.Style(color=False), 80)
    assert text == ("MAP\n\n"
                    "  1  A Paper\n"
                    "     Lovelace · CCS 2026 · core · not fetched · lovelace1843\n"
                    "     Because.")


def test_lines_view_is_one_tab_separated_line_per_paper(tmp_path):
    assert render.lines(LIST.entries(), Library(tmp_path)) == \
        "1\tlovelace1843\tnot fetched\tMap\tA Paper\t"


def test_fetch_line_aligns_columns():
    outcome = Outcome(LIST.entries()[0], Result.GOT, "arxiv 1")
    assert render.fetch_line(outcome, 14, render.Style(color=False)) == \
        "  got            lovelace1843    arxiv 1"
