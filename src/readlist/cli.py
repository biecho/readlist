"""readlist command line.

    readlist fetch reading-list.yaml            download open copies to ./papers/
    readlist fetch refs.bib --bbl build/main.bbl --out references/
    readlist fetch refs.bib --groups reading-list.csv
    readlist fetch reading-list.yaml --browser  also get papers sites block (ACM, Cloudflare)
    readlist list reading-list.yaml             what you have, what is missing
    readlist rank reading-list.yaml             the reading order, read-first on top
    readlist open reading-list.yaml 4 7-9       open papers by their number in `rank`
    readlist open reading-list.yaml --section map --app "PDF Expert"
    readlist check reading-list.yaml --online   lint the list, verify arXiv ids
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from readlist import __version__, browser, commands, config, opener, readers, render
from readlist.http import Fetcher, Http
from readlist.library import Library
from readlist.model import FormatError, ReadingList, SelectionError

OPEN_LIMIT = 10  # opening more at once needs --all
MARKS = {"got": "x", "have": "x", "would": ">", "manual": "~", "failed": "!"}


def main(argv: list[str] | None = None, http: Fetcher | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        full = readers.read(args.list, bbl=args.bbl, groups=args.groups)
        reading_list = full.select(group=args.group, tag=args.tag, section=args.section)
    except (FormatError, SelectionError, OSError) as problem:
        print(f"readlist: {problem}", file=sys.stderr)
        return 2
    args.positions = full.positions()

    http = http or Http()
    if args.command == "fetch":
        return _fetch(args, reading_list, http)
    elif args.command == "list":
        return _list(args, reading_list)
    elif args.command == "rank":
        return _rank(args, reading_list)
    elif args.command == "check":
        return _check(args, reading_list, http)
    elif args.command == "open":
        return _open(args, full, reading_list)
    else:
        raise AssertionError(f"unknown command {args.command}")


def _fetch(args, reading_list: ReadingList, http: Fetcher) -> int:
    if args.browser and not browser.available():
        print("readlist: --browser needs the browser-use CLI (pip install browser-use)",
              file=sys.stderr)
        return 2

    library = Library(_out_dir(args))
    with contextlib.ExitStack() as stack:
        window = stack.enter_context(browser.Browser()) if args.browser else None
        outcomes = commands.fetch(
            reading_list, library, http, config.load(),
            force=args.force, dry_run=args.dry_run, record=args.record, browser=window,
            report=lambda o: print(f"  [{MARKS[o.status]}] {o.status:<6} {o.paper.id}  {o.detail}"),
        )

    failed = [o for o in outcomes if o.status == "failed"]
    manual = [o for o in outcomes if o.status == "manual"]
    where = f" (see the .url files in {library.root})" if manual else ""
    print(f"\n{len(outcomes)} papers: {len(failed)} failed, {len(manual)} need a manual fetch{where}.")
    return 1 if failed else 0


def _list(args, reading_list: ReadingList) -> int:
    """Papers by group, numbered by their position in the group (the filename prefix)."""
    sections = [(title, [(p.number or i, p) for i, p in enumerate(papers, start=1)])
                for title, papers in reading_list.by_group()]
    _show(args, reading_list, sections)
    return 0


def _rank(args, reading_list: ReadingList) -> int:
    """Papers in reading order. Numbers come from the whole list, so filters keep them."""
    sections, unranked = reading_list.ranked()
    numbered = [(title, [(args.positions[p.id], p) for p in papers]) for title, papers in sections]

    _show(args, reading_list, numbered)
    if unranked:
        print(f"\nNot in the ranking: {', '.join(p.id for p in unranked)}")
    return 0


def _open(args, full: ReadingList, reading_list: ReadingList) -> int:
    """Open picked papers: PDFs in the PDF app, placeholders in the browser."""
    try:
        papers = full.pick(args.papers) if args.papers else list(reading_list.papers)
    except SelectionError as problem:
        print(f"readlist: {problem}", file=sys.stderr)
        return 2
    if args.papers:
        selected = {p.id for p in reading_list.papers}
        papers = [p for p in papers if p.id in selected]

    if not papers:
        print("readlist: nothing selected. Name papers by number or id, or use --section,"
              " --group or --tag.", file=sys.stderr)
        return 2
    if not args.papers and len(papers) > OPEN_LIMIT and not args.all:
        print(f"readlist: that selects {len(papers)} papers; add --all to open them all.",
              file=sys.stderr)
        return 2

    library = Library(_out_dir(args))
    app = args.app or config.load().pdf_app
    not_fetched = []
    for paper in sorted(papers, key=lambda p: args.positions[p.id]):
        number = args.positions[paper.id]
        link = library.placeholder_target(paper)
        if library.has(paper):
            opener.open_pdf(library.pdf_path(paper), app)
            print(f"  {number:>2}  {paper.title}")
        elif link and paper.link_only:
            opener.open_url(link)
            print(f"  {number:>2}  {paper.title}  ({paper.kind}: opened {link})")
        elif link:
            opener.open_url(link)
            print(f"  {number:>2}  {paper.title}  (fetch by hand: opened {link})")
        else:
            not_fetched.append(paper)

    for paper in not_fetched:
        print(f"  {args.positions[paper.id]:>2}  {paper.title}  (not fetched; run readlist fetch)")
    return 1 if not_fetched else 0


def _show(args, reading_list: ReadingList, sections) -> None:
    library = Library(_out_dir(args))
    style = render.Style.for_stdout()
    print(render.entries(sections, library, style, render.terminal_width()))
    print()
    print(render.summary(list(reading_list.papers), library, style))


def _check(args, reading_list: ReadingList, http: Fetcher) -> int:
    problems = commands.check(reading_list, http if args.online else None)
    for problem in problems:
        print(f"  {problem}")
    print(f"{len(reading_list.papers)} papers, {len(problems)} problems.")
    return 1 if problems else 0


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
    common.add_argument("--section", help="only this section of the ranking (e.g. Map)")
    common.add_argument("--out", type=Path, help="PDF folder (default: papers/ next to the list)")

    commands_ = parser.add_subparsers(dest="command", required=True)
    fetch = commands_.add_parser("fetch", parents=[common], help="download open copies")
    fetch.add_argument("--dry-run", action="store_true", help="resolve links, download nothing")
    fetch.add_argument("--force", action="store_true", help="re-download (annotated copies are backed up)")
    fetch.add_argument("--record", action="store_true", help="write discovered links back into the list")
    fetch.add_argument("--browser", action="store_true",
                       help="retry papers that sites block in a visible browser (needs browser-use)")
    commands_.add_parser("list", parents=[common], help="show what you have and what is missing")
    commands_.add_parser("rank", parents=[common], help="show the reading order, read-first on top")
    open_ = commands_.add_parser("open", parents=[common], help="open papers in your PDF app")
    open_.add_argument("papers", nargs="*", help="reading-order numbers (4), ranges (4-8) or ids")
    open_.add_argument("--app", help='PDF app, e.g. "PDF Expert" (default: pdf_app in config)')
    open_.add_argument("--all", action="store_true", help=f"allow opening more than {OPEN_LIMIT} papers")
    check = commands_.add_parser("check", parents=[common], help="lint the list")
    check.add_argument("--online", action="store_true", help="also verify arXiv ids against titles")
    return parser


if __name__ == "__main__":
    sys.exit(main())
