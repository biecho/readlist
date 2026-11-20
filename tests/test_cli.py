import json

import pytest

from conftest import PDF, FakeHttp
from readlist import cli

LIST = """
ranking:
  Map: [b, a]
groups:
  - id: 01-map
    title: Get the map
    papers:
      - {id: a, title: Paper A, pdf: "https://x/a.pdf", tags: [core]}
      - {id: b, title: Paper B, kind: talk, landing: "https://talk"}
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "reading-list.yaml").write_text(LIST)
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")  # the list is found in a parent folder
    return tmp_path


def test_ls_piped_prints_one_line_per_paper(project, capsys):
    assert cli.main(["ls"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["1\tb\tlink\tMap\tPaper B\thttps://talk",
                   "2\ta\tnot fetched\tMap\tPaper A\t"]


def test_ls_json_missing_and_filters(project, capsys):
    assert cli.main(["ls", "--json", "--missing"]) == 0
    assert [r["id"] for r in json.loads(capsys.readouterr().out)] == ["a"]
    assert cli.main(["ls", "-s", "get the map", "-t", "core"]) == 0
    assert capsys.readouterr().out.startswith("2\ta\t")


def test_list_options_work_before_or_after_the_command(project, capsys, tmp_path):
    other = tmp_path / "other.yaml"
    other.write_text("papers:\n  - {id: z, title: Z}\n")
    assert cli.main(["ls", "-f", str(other)]) == 0
    assert cli.main(["-f", str(other), "ls"]) == 0
    assert capsys.readouterr().out.count("\tz\t") == 2


def test_fetch_is_quiet_about_what_you_have(project, capsys):
    http = FakeHttp({"https://x/a.pdf": PDF})
    assert cli.main(["fetch"], http=http) == 0
    first = capsys.readouterr()
    assert "got" in first.out and "1 got" in first.err
    assert cli.main(["fetch"], http=http) == 0
    second = capsys.readouterr()
    assert second.out == "" and "1 already here" in second.err


def test_errors_are_one_line(project, capsys, tmp_path):
    assert cli.main(["ls", "-f", str(tmp_path / "nope.yaml")]) == 2
    assert capsys.readouterr().err.strip().endswith("nope.yaml: no such file")
    assert cli.main(["ls", "-s", "nope"]) == 2
    assert "choose from: Map, 01-map" in capsys.readouterr().err
    assert cli.main(["open", "1", "-s", "map"]) == 2
    assert "not both" in capsys.readouterr().err


def test_no_list_anywhere(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["ls"]) == 2
    assert "no reading-list.yaml here or in a parent folder" in capsys.readouterr().err


def test_check_reports_ranking_problems(project, capsys):
    (project / "reading-list.yaml").write_text(LIST.replace("[b, a]", "[b, a, zz]"))
    assert cli.main(["check"]) == 1
    assert "ranking names unknown id 'zz'" in capsys.readouterr().out
