# readlist

readlist turns a reading list in your repository into a local folder of PDFs,
in the order you mean to read them. Your group commits the list; each person
runs `readlist fetch` and gets the same papers on their own machine.

```
uv tool install git+https://github.com/biecho/readlist
cd my-project            # has a reading-list.yaml
readlist fetch           # download open copies
readlist ls              # the reading order, with what you have
readlist open 4 7-9      # open papers by number in your PDF app
```

```
MAP

  1  SoK: Understanding Design Choices and Pitfalls of Trusted Execution Environments
     Li et al. · AsiaCCS 2024 · core · downloaded · li2024sok-tee-pitfalls
     Design space of TEEs, mapped to the attack class each choice invites.

  2  Let's Get Physical: Low-Cost Memory Interposer Attacks and the Future of ...
     Van Bulck · SysTEX keynote 2026 · talk · core · downloaded · vanbulck2026systex-keynote
     The field's current headline in one talk (slides).
```

Every paper has one number, its place in the reading order. Filters never
renumber, so paper 8 is paper 8 in `ls`, `ls -s frontier` and `open 8`.

## What it guarantees

- **Your annotations survive.** readlist never re-downloads a PDF you have.
  If `--force` would replace a file you highlighted, readlist first moves your
  copy to `annotated-backup/`.
- **Looking changes nothing.** `ls`, `open` and `check` only read; `fetch` is
  the one command that writes.
- **You get the right paper.** readlist checks every arXiv id against the
  paper's title and reports a mismatch instead of saving the wrong PDF.
- **The PDFs stay out of the repository.** You share the list and keep the
  copyrighted papers local.

## Commands

```
readlist ls     [-s SECTION] [-t TAG] [--missing] [--json]
readlist fetch  [-s SECTION] [-t TAG] [-n] [--force] [--record] [--browser] [-v]
readlist open   [N | N-M | ID ...] [-s SECTION] [-t TAG] [--app APP] [--all]
readlist check  [--online]
```

- `-s` picks a ranking section or a group, by title or id, ignoring case
  (`-s map`). `-t` picks a tag (`-t core`). A filter that matches nothing is
  an error that lists the valid choices.
- `ls` prints the reading view on a terminal. In a pipe it prints one
  tab-separated line per paper: number, id, status, section, title, and path
  or link. `--json` prints JSON.
- `fetch` reports only what changed or needs you; `-v` lists everything.
  `-n` shows what it would do.
- `open` opens PDFs in your PDF app, and talks or papers to fetch by hand in
  your browser. Opening more than 10 papers by filter needs `--all`.

readlist finds `reading-list.yaml` (or `.yml`, `.bib`, `.csv`) in the current
folder or a parent, the way git finds `.git`. These options name the list,
before or after the command:

```
-f FILE        another list
--bbl FILE     with a .bib list: keep cited entries, in citation order
--folders CSV  give each paper id a folder (columns: id, group)
--out DIR      the PDF folder (default: papers/ next to the list)
```

## Write a list

```yaml
ranking:                        # the reading order, optionally in sections
  Map:
    - li2024sok
  Designs:
    - lee2020keystone
  Foundations:
    - costan2016sgx

groups:                         # folders under papers/
  - id: 01-basics
    title: Basics
    papers:
      - id: costan2016sgx
        title: Intel SGX Explained
        tags: [core]
        pdf: https://css.csail.mit.edu/6.858/2019/readings/costan-sgx.pdf
        why: The field's textbook. Use as a reference.
      - id: lee2020keystone
        title: "Keystone: An Open Framework for Architecting TEEs"
        arxiv: "1907.10119"     # quote it, or YAML turns 2010.08440 into 2010.0844
      - id: li2024sok
        title: "SoK: Understanding Design Choices and Pitfalls of TEEs"
        doi: 10.1145/3634737.3644993
```

readlist saves each paper as `papers/<group>/<id>.pdf`. Each paper needs an
`id` and a `title`; add `pdf`, `arxiv` or `doi` to help readlist find it.
Optional fields: `authors`, `year`, `venue`, `tags`, `why` (shown under the
title), `landing` (the page to open when there is no PDF), `kind: talk` or
`kind: web` (only an explicit `pdf`, such as slides, downloads), and
`open_copy: false` (online lookups would find the wrong version). readlist
ignores any other keys, so keep your reading notes in the list.

Without a `ranking:`, the file order is the reading order. `readlist check`
reports ranking ids that don't exist, repeat, or leave a paper out.
[`examples/reading-list.yaml`](examples/reading-list.yaml) shows a complete list.

BibTeX and CSV lists work too. In BibTeX, readlist uses `pdfurl`, `url` (when
it ends in `.pdf`), `eprint`, `doi` and `opencopy = {none}`. With `--bbl`, the
citation order is the reading order, so numbers match your paper's.

## How readlist finds a PDF

readlist tries these sources in order and stops at the first hit:

1. the `pdf` link in your list
2. the `arxiv` id, after the title check
3. [Unpaywall](https://unpaywall.org), by DOI (needs your email; see below)
4. [Semantic Scholar](https://www.semanticscholar.org), by DOI or title
5. an arXiv search by title

With `--record`, readlist writes each link it found through steps 3–5 back
into your list, so your collaborators skip the lookup.

### Papers a site blocks

Some publishers, ACM among them, refuse scripts but serve the same open PDF to
a person in a browser. With `--browser`, readlist retries those papers in a
visible browser window, one at a time:

```
pip install browser-use        # once; readlist drives its CLI
readlist fetch --browser
```

readlist tries the blocked link it found, and for ACM DOIs the ACM Digital
Library PDF. If the site shows a check that needs a click, click it in the
window; readlist waits up to a minute. The window uses a fresh browser profile
with none of your logins, so it gets only what the site gives any visitor.

## Configure

Put your settings in `~/.config/readlist/config.toml`:

```toml
email = "you@example.org"        # turns on Unpaywall
semantic_scholar_key = "..."     # optional: your own Semantic Scholar quota
pdf_app = "PDF Expert"           # optional: the app readlist open uses
```

`READLIST_EMAIL` and `S2_API_KEY` override the file.

## License

MIT
