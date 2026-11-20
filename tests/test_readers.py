from pathlib import Path

import pytest

from readlist import readers
from readlist.model import FormatError


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_yaml_groups_and_tags(tmp_path):
    path = write(tmp_path, "list.yaml", """
stages:
  - id: a
    title: Group A
    papers:
      - {id: p1, title: One, core: true}
      - {id: p2, title: Two, tags: [x]}
  - id: b
    papers:
      - {id: p3, title: Three, arxiv: "2010.08440"}
""")
    reading_list = readers.read(path)
    papers = reading_list.papers
    assert [(p.group, p.id) for p in papers] == [("a", "p1"), ("a", "p2"), ("b", "p3")]
    assert papers[0].tags == {"core"} and papers[2].arxiv == "2010.08440"
    assert reading_list.group_titles == {"a": "Group A", "b": ""}


def test_yaml_rejects_unquoted_arxiv_id(tmp_path):
    path = write(tmp_path, "list.yaml", "papers:\n  - {id: p, title: T, arxiv: 2010.08440}\n")
    with pytest.raises(FormatError, match="quote the arXiv id"):
        readers.read(path)


def test_yaml_requires_title(tmp_path):
    path = write(tmp_path, "list.yaml", "papers:\n  - {id: p}\n")
    with pytest.raises(FormatError, match="missing 'title'"):
        readers.read(path)


BIB = r"""
@string{sp = "IEEE S&P"}
@inproceedings{costan2016,
  title = {Intel {SGX} Explained},
  author = {Costan, Victor and Devadas, Srinivas},
  year = 2016,
  url = {https://example.org/sgx.pdf},
}
@article{lee2020, title = "Keystone: {A}n Open Framework", eprint = {1907.10119},
  archivePrefix = {arXiv}, doi = {10.1145/3342195.3387532}}
@misc{spec, title = {Some Spec}, url = {https://example.org/spec}}
@inproceedings{old, title = {Old}, eprint = {2001.00001}, opencopy = {none}}
"""


def test_bibtex_fields(tmp_path):
    papers = {p.id: p for p in readers.read(write(tmp_path, "refs.bib", BIB)).papers}
    assert papers["costan2016"].title == "Intel SGX Explained"
    assert papers["costan2016"].pdf == "https://example.org/sgx.pdf"
    assert papers["costan2016"].authors == ("Costan, Victor", "Devadas, Srinivas")
    assert papers["lee2020"].arxiv == "1907.10119"
    assert papers["lee2020"].landing == "https://doi.org/10.1145/3342195.3387532"
    assert papers["spec"].kind == "web"
    assert papers["old"].open_copy is False


def test_bibtex_bbl_keeps_cited_entries_in_citation_order(tmp_path):
    bib = write(tmp_path, "refs.bib", BIB)
    bbl = write(tmp_path, "main.bbl", r"\bibitem{lee2020} x \bibitem[Co16]{costan2016} y")
    reading_list = readers.read(bib, bbl=bbl)
    assert [(e.number, e.paper.id) for e in reading_list.entries()] == [(1, "lee2020"),
                                                                       (2, "costan2016")]


def test_csv_list_and_group_override(tmp_path):
    listing = write(tmp_path, "list.csv", "id,title,tags\na,Paper A,core;x\nb,Paper B,\n")
    groups = write(tmp_path, "groups.csv", "citekey,cluster\na,costs\n")
    papers = readers.read(listing, folders=groups).papers
    assert [(p.id, p.group) for p in papers] == [("a", "costs"), ("b", "unsorted")]
    assert papers[0].tags == {"core", "x"}


def test_unknown_format(tmp_path):
    with pytest.raises(FormatError, match="unsupported format"):
        readers.read(write(tmp_path, "list.txt", ""))



def test_ranking_sections_keep_their_titles(tmp_path):
    path = write(tmp_path, "l.yaml", """
ranking:
  Start: [b]
  Then: [a]
papers:
  - {id: a, title: A, read_for: Second.}
  - {id: b, title: B, why: First.}
""")
    reading_list = readers.read(path)
    assert [(s.title, s.ids) for s in reading_list.ranking] == [("Start", ("b",)), ("Then", ("a",))]
    assert reading_list.papers[0].why == "Second." and reading_list.papers[1].why == "First."


def test_ranking_with_unknown_ids_still_reads(tmp_path):
    path = write(tmp_path, "l.yaml", "ranking: [a, z, a]\npapers:\n  - {id: a, title: A}\n")
    assert readers.read(path).ranking_problems() == [
        "ranking names unknown id 'z'", "ranking repeats 'a'"]


def test_invalid_yaml_reports_file_and_line(tmp_path):
    with pytest.raises(FormatError, match=r"l\.yaml:2: mapping values are not allowed here"):
        readers.read(write(tmp_path, "l.yaml", "ranking:\n  A: b: c\n"))


def test_missing_file(tmp_path):
    with pytest.raises(FormatError, match="nope.yaml: no such file"):
        readers.read(tmp_path / "nope.yaml")
