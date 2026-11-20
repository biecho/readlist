"""readlist: keep a reading list in git; fetch and open its open-access PDFs.

    readlist ls                  the reading order, with what you have
    readlist ls -s map           one section (or group)
    readlist fetch               download what is missing
    readlist open 4 7-9          open papers by number or id
    readlist check               lint the list

readlist finds reading-list.{yaml,yml,bib,csv} in this folder or a parent;
-f names another list. Numbers are the reading order and never change with
filters, so `ls` and `open` always agree.
"""

from __future__ import annotations

import argparse
import contextlib
import signal
import sys
from pathlib import Path

from readlist import __version__, browser, commands, config, opener, readers, render
from readlist.http import Fetcher, Http
from readlist.library import Availability, Library
from readlist.model import FormatError, ReadingList, SelectionError, pick, select

LIST_NAMES = ("reading-list.yaml", "reading-list.yml", "reading-list.bib", "reading-list.csv")


def main(argv: list[str] | None = None, http: Fetcher | None = None) -> int:
    _die_quietly_on_closed_pipe()
    args = _parser().parse_args(argv)
    try:
        list_path = args.file or find_list(Path.cwd())
        reading_list = readers.read(list_path, bbl=args.bbl, folders=args.folders)
        library = Library(args.out or list_path.resolve().parent / "papers")
        return COMMANDS[args.command](args, reading_list, library, http or Http())
    except (FormatError, SelectionError) as problem:
        return _fail(str(problem))
    except OSError as problem:
        return _fail(_describe(problem))


def find_list(start: Path) -> Path:
    """The nearest reading list in `start` or a parent folder, the way git finds .git."""
    for folder in (start, *start.parents):
        for name in LIST_NAMES:
            if (folder / name).is_file():
                return folder / name
    raise FormatError("no reading-list.yaml here or in a parent folder (use -f FILE)")


# --- commands ------------------------------------------------------------------

def _ls(args, reading_list: ReadingList, library: Library, http: Fetcher) -> int:
    entries = select(reading_list, section=args.section, tag=args.tag)
    if args.missing:
        done = (Availability.DOWNLOADED, Availability.LINK)
        entries = [e for e in entries if library.state(e.paper).availability not in done]

    if args.json:
        print(render.as_json(entries, library))
    elif render.stdout_is_terminal():
        if entries:
            print(render.terminal(entries, library, render.Style.for_stream(sys.stdout),
                                  render.terminal_width()))
            print()
        _note(render.summary(entries, library, render.Style.for_stream(sys.stderr)))
    elif entries:
        print(render.lines(entries, library))

    _warn_about_ranking(reading_list)
    return 0


def _fetch(args, reading_list: ReadingList, library: Library, http: Fetcher) -> int:
    if args.browser and not browser.available():
        return _fail("--browser needs the browser-use CLI (pip install browser-use)")

    entries = select(reading_list, section=args.section, tag=args.tag)
    options = commands.FetchOptions(force=args.force, dry_run=args.dry_run,
                                    record_into=reading_list.source if args.record else None)
    style = render.Style.for_stream(sys.stdout)
    id_width = max((len(e.paper.id) for e in entries), default=0)
    quiet = (commands.Result.HAVE, commands.Result.LINK)

    def report(outcome: commands.Outcome) -> None:
        if args.verbose or outcome.result not in quiet:
            print(render.fetch_line(outcome, id_width, style), flush=True)

    with contextlib.ExitStack() as stack:
        window = stack.enter_context(browser.Browser()) if args.browser else None
        outcomes = commands.fetch(entries, library, http, config.load(), options, window, report)

    _note(_fetch_summary(outcomes))
    _warn_about_ranking(reading_list)
    return 1 if any(o.result is commands.Result.FAILED for o in outcomes) else 0


def _open(args, reading_list: ReadingList, library: Library, http: Fetcher) -> int:
    if args.papers and (args.section or args.tag):
        return _fail("name papers by number/id, or select them with -s/-t, not both")

    entries = (pick(reading_list, args.papers) if args.papers
               else select(reading_list, section=args.section, tag=args.tag))
    commands.check_open_count(entries, picked=bool(args.papers), allow_many=args.all)

    app = args.app or config.load().pdf_app
    results = commands.open_entries(entries, library,
                                    open_pdf=lambda path: opener.open_pdf(path, app),
                                    open_url=opener.open_url)
    for result in results:
        print(_open_line(result))
    return 1 if any(r.opened is commands.Opened.NOT_FETCHED for r in results) else 0


def _check(args, reading_list: ReadingList, library: Library, http: Fetcher) -> int:
    problems = commands.check(reading_list, http if args.online else None)
    for problem in problems:
        print(problem)
    _note(f"{len(reading_list.papers)} papers, {len(problems)} "
          f"{'problem' if len(problems) == 1 else 'problems'}")
    return 1 if problems else 0


COMMANDS = {"ls": _ls, "fetch": _fetch, "open": _open, "check": _check}


# --- output helpers ------------------------------------------------------------

def _fetch_summary(outcomes: list[commands.Outcome]) -> str:
    counts = {r: sum(1 for o in outcomes if o.result is r) for r in commands.Result}
    parts = [f"{len(outcomes)} papers"]
    for result, word in ((commands.Result.GOT, "got"), (commands.Result.WOULD_GET, "would get"),
                         (commands.Result.HAVE, "already here"),
                         (commands.Result.FETCH_BY_HAND, "to fetch by hand"),
                         (commands.Result.FAILED, "failed")):
        if counts[result]:
            parts.append(f"{counts[result]} {word}")
    return ", ".join(parts)


def _open_line(result: commands.OpenResult) -> str:
    entry = result.entry
    line = f"{entry.number:>3}  {entry.paper.title}"
    if result.opened is commands.Opened.PDF:
        return line
    elif result.opened is commands.Opened.LINK:
        return f"{line}  ({entry.paper.kind}: opened {result.target})"
    elif result.opened is commands.Opened.FETCH_BY_HAND:
        return f"{line}  (fetch by hand: opened {result.target})"
    elif result.opened is commands.Opened.NOT_FETCHED:
        return f"{line}  (not fetched: run readlist fetch)"
    else:
        raise AssertionError(f"unknown result {result.opened}")


def _warn_about_ranking(reading_list: ReadingList) -> None:
    problems = reading_list.ranking_problems()
    if problems:
        _note(f"readlist: {len(problems)} ranking {'problem' if len(problems) == 1 else 'problems'}"
              f" (run readlist check)")


def _note(message: str) -> None:
    print(message, file=sys.stderr)


def _fail(message: str) -> int:
    _note(f"readlist: {message}")
    return 2


def _describe(problem: OSError) -> str:
    """'nope.csv: no such file', not '[Errno 2] No such file or directory: ...'."""
    reason = (problem.strerror or str(problem)).lower().replace(" or directory", "")
    return f"{problem.filename}: {reason}" if problem.filename else reason


def _die_quietly_on_closed_pipe() -> None:
    """`readlist ls | head` should just stop, without a BrokenPipeError traceback."""
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


# --- arguments -----------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="readlist", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"readlist {__version__}")
    _add_input_options(parser, keep_default=True)

    subcommands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    ls = _subcommand(subcommands, "ls", "show the reading order and what you have")
    _add_filters(ls)
    ls.add_argument("--missing", action="store_true", help="only papers you don't have yet")
    ls.add_argument("--json", action="store_true", help="print JSON")

    fetch = _subcommand(subcommands, "fetch", "download open copies of what is missing")
    _add_filters(fetch)
    fetch.add_argument("-n", "--dry-run", action="store_true", help="find links, change nothing")
    fetch.add_argument("--force", action="store_true",
                       help="re-download PDFs you have (annotated copies are backed up)")
    fetch.add_argument("--record", action="store_true",
                       help="write links readlist found back into the list")
    fetch.add_argument("--browser", action="store_true",
                       help="retry papers a site blocks in a visible browser (needs browser-use)")
    fetch.add_argument("-v", "--verbose", action="store_true",
                       help="also list papers you already have")

    open_ = _subcommand(subcommands, "open", "open papers in your PDF app")
    open_.add_argument("papers", nargs="*", metavar="N|N-M|ID",
                       help="numbers from `readlist ls`, ranges, or paper ids")
    _add_filters(open_)
    open_.add_argument("--app", help='PDF app, e.g. "PDF Expert" (default: pdf_app in config)')
    open_.add_argument("--all", action="store_true",
                       help=f"allow opening more than {commands.OPEN_LIMIT} papers by filter")

    check = _subcommand(subcommands, "check", "lint the list")
    check.add_argument("--online", action="store_true",
                       help="also verify arXiv ids against paper titles")
    return parser


def _subcommand(subcommands, name: str, help_text: str) -> argparse.ArgumentParser:
    sub = subcommands.add_parser(name, help=help_text, description=help_text)
    _add_input_options(sub, keep_default=False)
    return sub


def _add_input_options(parser: argparse.ArgumentParser, *, keep_default: bool) -> None:
    """Which list to read; accepted before or after the command."""
    default = None if keep_default else argparse.SUPPRESS
    group = parser.add_argument_group("list")
    group.add_argument("-f", "--file", type=Path, default=default,
                       help="the reading list (default: reading-list.yaml here or in a parent)")
    group.add_argument("--bbl", type=Path, default=default,
                       help="with a .bib list: keep cited entries, in citation order")
    group.add_argument("--folders", type=Path, default=default,
                       help="CSV giving each paper id a folder (id + group columns)")
    group.add_argument("--out", type=Path, default=default,
                       help="PDF folder (default: papers/ next to the list)")


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-s", "--section",
                        help="a ranking section or group, by title or id (e.g. map)")
    parser.add_argument("-t", "--tag", help="papers with this tag (e.g. core)")


if __name__ == "__main__":
    sys.exit(main())
