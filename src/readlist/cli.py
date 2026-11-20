"""readlist command line.

    readlist fetch reading-list.yaml            download open copies to ./papers/
    readlist fetch refs.bib --bbl build/main.bbl --out references/
    readlist fetch refs.bib --groups reading-list.csv
    readlist list reading-list.yaml             what you have, what is missing
    readlist check reading-list.yaml --online   lint the list, verify arXiv ids
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from readlist import __version__, commands, config, readers
from readlist.http import Fetcher, Http
from readlist.library import Library
from readlist.model import FormatError, ReadingList

MARKS = {"have": "x", "got": "x", "would": ">", "manual": "~", "failed": "!", "missing": " "}


def main(argv: list[str] | None = None, http: Fetcher | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        reading_list = _load(args)
    except (FormatError, OSError) as problem:
        print(f"readlist: {problem}", file=sys.stderr)
        return 2

    http = http or Http()
    if args.command == "fetch":
        return _fetch(args, reading_list, http)
    elif args.command == "list":
        return _list(args, reading_list)
    elif args.command == "check":
        return _check(args, reading_list, http)
    else:
        raise AssertionError(f"unknown command {args.command}")


def _fetch(args, reading_list: ReadingList, http: Fetcher) -> int:
    library = Library(_out_dir(args))
    outcomes = commands.fetch(
        reading_list, library, http, config.load(),
        force=args.force, dry_run=args.dry_run, record=args.record,
        report=lambda o: print(f"  [{MARKS[o.status]}] {o.status:<6} {o.paper.id}  {o.detail}"),
    )

    failed = [o for o in outcomes if o.status == "failed"]
    manual = [o for o in outcomes if o.status == "manual"]
    print(f"\n{len(outcomes)} papers: {len(failed)} failed, {len(manual)} need a manual fetch"
          f" (see the .url files in {library.root}).")
    return 1 if failed else 0


def _list(args, reading_list: ReadingList) -> int:
    library = Library(_out_dir(args))
    for group in reading_list.groups():
        print(group or "(ungrouped)")
        for paper in reading_list.select(group=group).papers:
            status = library.status(paper)
            star = "*" if "core" in paper.tags else " "
            print(f"  [{MARKS[status]}]{star} {paper.stem}  {paper.title}")
    print("\n[x] have  [~] manual fetch  [ ] not fetched yet   * core")
    return 0


def _check(args, reading_list: ReadingList, http: Fetcher) -> int:
    problems = commands.check(reading_list, http if args.online else None)
    for problem in problems:
        print(f"  {problem}")
    print(f"{len(reading_list.papers)} papers, {len(problems)} problems.")
    return 1 if problems else 0


def _load(args) -> ReadingList:
    reading_list = readers.read(args.list, bbl=args.bbl, groups=args.groups)
    return reading_list.select(group=args.group, tag=args.tag)


def _out_dir(args) -> Path:
    return args.out if args.out else args.list.resolve().parent / "papers"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="readlist", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"readlist {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("list", type=Path, help="reading list: .yaml, .bib or .csv")
    common.add_argument("--bbl", type=Path, help="with a .bib: keep cited entries, number as in the paper")
    common.add_argument("--groups", type=Path, help="CSV assigning each id a folder (id/citekey + group/cluster)")
    common.add_argument("--group", help="only this group")
    common.add_argument("--tag", help="only papers with this tag (e.g. core)")
    common.add_argument("--out", type=Path, help="PDF folder (default: papers/ next to the list)")

    commands_ = parser.add_subparsers(dest="command", required=True)
    fetch = commands_.add_parser("fetch", parents=[common], help="download open copies")
    fetch.add_argument("--dry-run", action="store_true", help="resolve links, download nothing")
    fetch.add_argument("--force", action="store_true", help="re-download (annotated copies are backed up)")
    fetch.add_argument("--record", action="store_true", help="write discovered links back into the list")
    commands_.add_parser("list", parents=[common], help="show what you have and what is missing")
    check = commands_.add_parser("check", parents=[common], help="lint the list")
    check.add_argument("--online", action="store_true", help="also verify arXiv ids against titles")
    return parser


if __name__ == "__main__":
    sys.exit(main())
