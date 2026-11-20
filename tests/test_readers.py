from pathlib import Path

import pytest

from readlist import readers
from readlist.model import FormatError


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_yaml_groups_number_papers_within_each_group(tmp_path):
    path = write(tmp_path, "list.yaml", """
stages:
  - id: a
    papers:
      - {id: p1, title: One, core: true}
      - {id: p2, title: Two, tags: [x]}
  - id: b
    papers:
      - {id: p3, title: Three, arxiv: "2010.08440"}
""")
    papers = readers.read(path).papers
    assert [(p.group, p.stem) for p in papers] == [("a", "01-p1"), ("a", "02-p2"), ("b", "01-p3")]
    assert papers[0].tags == {"core"}
    assert papers[2].arxiv == "2010.08440"


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
    papers = readers.read(bib, bbl=bbl).papers
    assert [p.stem for p in papers] == ["01-lee2020", "02-costan2016"]


def test_csv_list_and_group_override(tmp_path):
    listing = write(tmp_path, "list.csv", "id,title,tags\na,Paper A,core;x\nb,Paper B,\n")
    groups = write(tmp_path, "groups.csv", "citekey,cluster\na,costs\n")
    papers = readers.read(listing, groups=groups).papers
    assert [(p.id, p.group) for p in papers] == [("a", "costs"), ("b", "unsorted")]
    assert papers[0].tags == {"core", "x"}


def test_unknown_format(tmp_path):
    with pytest.raises(FormatError, match="unsupported format"):
        readers.read(write(tmp_path, "list.txt", ""))
