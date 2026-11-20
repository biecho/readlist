from pathlib import Path

import pytest

from readlist.model import (UNRANKED_SECTION, FormatError, Paper, ReadingList, Section,
                            SelectionError, pick, select)

PAPERS = (
    Paper(id="a", title="A", group="01-map", tags=frozenset({"core"})),
    Paper(id="b", title="B", group="01-map"),
    Paper(id="c", title="C", group="02-deep"),
    Paper(id="d", title="D", group="02-deep"),
)
RANKED = ReadingList(source=Path("l.yaml"), papers=PAPERS,
                     ranking=(Section("Map", ("b", "a")), Section("Deep", ("c",))),
                     group_titles={"01-map": "Get the map", "02-deep": "Go deep"})


def numbers(entries):
    return [(e.number, e.paper.id) for e in entries]


def test_ranking_is_the_reading_order_and_unranked_papers_follow():
    entries = RANKED.entries()
    assert numbers(entries) == [(1, "b"), (2, "a"), (3, "c"), (4, "d")]
    assert [e.section for e in entries] == ["Map", "Map", "Deep", UNRANKED_SECTION]


def test_without_ranking_the_file_order_is_the_reading_order():
    plain = ReadingList(source=Path("l.yaml"), papers=PAPERS,
                        group_titles={"01-map": "Get the map"})
    assert numbers(plain.entries()) == [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
    assert plain.entries()[0].section == "Get the map"
    assert plain.entries()[2].section == "02-deep"  # no title: the id


def test_filters_keep_numbers():
    assert numbers(select(RANKED, tag="core")) == [(2, "a")]
    assert numbers(select(RANKED, section="deep")) == [(3, "c")]


def test_section_matches_ranking_title_group_id_or_group_title():
    assert numbers(select(RANKED, section="MAP")) == [(1, "b"), (2, "a")]
    assert numbers(select(RANKED, section="02-deep")) == [(3, "c"), (4, "d")]
    assert numbers(select(RANKED, section="go deep")) == [(3, "c"), (4, "d")]


def test_a_selector_that_matches_nothing_is_an_error_listing_choices():
    with pytest.raises(SelectionError, match="choose from: Map, Deep, 01-map, 02-deep"):
        select(RANKED, section="nope")
    with pytest.raises(SelectionError, match=r"tags: core"):
        select(RANKED, tag="Core")


def test_pick_by_number_range_and_id_in_reading_order():
    assert numbers(pick(RANKED, ["c", "1"])) == [(1, "b"), (3, "c")]
    assert numbers(pick(RANKED, ["1-2", "a"])) == [(1, "b"), (2, "a")]
    with pytest.raises(SelectionError, match="numbers run from 1 to 4"):
        pick(RANKED, ["7"])
    with pytest.raises(SelectionError, match="neither a paper id nor a number"):
        pick(RANKED, ["nope"])


def test_ranking_problems():
    broken = ReadingList(source=Path("l.yaml"), papers=PAPERS[:2],
                         ranking=(Section("", ("a", "x", "a")),))
    assert broken.ranking_problems() == [
        "ranking names unknown id 'x'", "ranking repeats 'a'", "'b' is not in the ranking"]
    assert numbers(broken.entries()) == [(1, "a"), (2, "b")]
