# readlist

readlist turns a reading list in your repository into a local folder of PDFs.
Your group commits the list; each person runs `readlist fetch` and gets the
same papers, in the same order, on their own machine.

```
uv tool install git+https://github.com/biecho/readlist
readlist fetch reading-list.yaml
```

```
  [x] got    costan2016sgx    pdf link in list
  [x] got    lee2020keystone  arxiv 1907.10119
  [x] got    xu2015controlled semantic scholar
  [~] manual li2024sok        papers/01-map/01-li2024sok.url
  [x] have   yu2023capstone   papers/05-angle/01-yu2023capstone.pdf
```

readlist downloads only open copies. When it finds none, it writes a `.url`
file that opens the paper's page, so you fetch that one by hand, or let
`--browser` fetch it for you.

## What it guarantees

- **Your annotations survive.** readlist never re-downloads a PDF you have.
  If `--force` would replace a file you highlighted, readlist first moves your
  copy to `annotated-backup/`.
- **You get the right paper.** readlist checks every arXiv id against the
  paper's title and reports a mismatch instead of saving the wrong PDF.
- **The PDFs stay out of the repository.** You share the list, which you can
  review like code, and keep the copyrighted papers local.

## Write a list

```yaml
groups:
  - id: 01-map
    title: Get the map
    papers:
      - id: costan2016sgx
        title: Intel SGX Explained
        tags: [core]
        pdf: https://css.csail.mit.edu/6.858/2019/readings/costan-sgx.pdf
      - id: lee2020keystone
        title: "Keystone: An Open Framework for Architecting TEEs"
        arxiv: "1907.10119"     # quote it, or YAML turns 2010.08440 into 2010.0844
```

readlist saves each paper as `papers/<group>/<NN>-<id>.pdf`, where NN is its
position in the group. Each paper needs an `id` and a `title`; add `pdf`,
`arxiv` or `doi` to help readlist find it. Optional fields: `authors`, `year`,
`venue`, `tags`, `landing` (the page a `.url` file opens), `kind: talk` or
`kind: web` (link only, never downloaded), and `open_copy: false` (accept only
the `pdf` link). readlist ignores any other keys, so keep your reading notes in
the list. [`examples/reading-list.yaml`](examples/reading-list.yaml) shows a
complete list.

### Rank what to read first

Groups and positions say where a paper belongs; a top-level `ranking:` says
when to read it. List paper ids from read-first to read-last, across groups,
optionally under section titles:

```yaml
ranking:
  Map:
    - li2024sok
  Designs:
    - lee2020keystone
  Foundations:
    - costan2016sgx
```

`readlist rank` prints that order with each paper's authors, venue, status
and its `why` (or `read_for`) line. A plain list of ids works too. readlist
rejects a ranking that names an unknown id or repeats one, and lists the
papers it leaves out.

```
$ readlist rank reading-list.yaml
MAP

  1  SoK: Understanding Design Choices and Pitfalls of Trusted Execution Environments
     Li et al. · AsiaCCS 2024 · core · fetch by hand
     Design space of TEEs, mapped to the attack class each choice invites.

DESIGNS

  2  Keystone: An Open Framework for Architecting TEEs
     Lee et al. · EuroSys 2020 · core · downloaded
     Open RISC-V TEE; the academic prototyping base.

3 papers · 2 downloaded · 1 to fetch by hand (open the .url files in papers/)
```

### Open what you picked

`readlist open` opens papers by their number in `readlist rank`, by range,
by id, or by ranking section. It opens downloaded PDFs in your PDF app, and
the page of any paper you still have to fetch by hand in your browser.

```
readlist open reading-list.yaml 4 7-9            # numbers stay fixed, even with filters
readlist open reading-list.yaml badram
readlist open reading-list.yaml --section map --app "PDF Expert"
```

Set `pdf_app` in your config to skip `--app`. Opening more than 10 papers at
once needs `--all`.

readlist also reads BibTeX and CSV:

```
readlist fetch refs.bib                              # every entry
readlist fetch refs.bib --bbl build/main.bbl         # cited entries, numbered as in your paper
readlist fetch refs.bib --groups reading-list.csv    # one folder per group
readlist fetch papers.csv                            # columns: id, title, group, pdf, arxiv, doi, ...
```

In BibTeX, readlist uses `pdfurl`, `url` (when it ends in `.pdf`), `eprint`
and `doi`. Mark an entry `opencopy = {none}` when its only open copy is a
different version, such as a superseded preprint.

## How readlist finds a PDF

readlist tries these sources in order and stops at the first hit:

1. the `pdf` link in your list
2. the `arxiv` id, after the title check
3. [Unpaywall](https://unpaywall.org), by DOI (needs your email; see below)
4. [Semantic Scholar](https://www.semanticscholar.org), by DOI or title
5. an arXiv search by title

Add `--record` and readlist writes each link it found through steps 3–5 back
into your list, so your collaborators skip the lookup.

### Papers a site blocks

Some publishers, ACM among them, refuse scripts but serve the same open PDF to
a person in a browser. Add `--browser` and readlist retries those papers in a
visible browser window, one at a time:

```
pip install browser-use        # once; readlist drives its CLI
readlist fetch reading-list.yaml --browser
```

readlist tries the blocked link it found, and for ACM DOIs the ACM Digital
Library PDF. If the site shows a bot check that needs a click, click it in the
window; readlist waits up to a minute. The window uses a fresh browser profile
with none of your logins, so it gets only what the site gives any visitor.

## Commands

```
readlist fetch LIST [--dry-run] [--force] [--record] [--browser]
readlist list  LIST               # what you have, what still needs a manual fetch
readlist rank  LIST               # the reading order, read-first on top
readlist open  LIST [N|N-M|ID ...] [--app APP]   # open papers in your PDF app
readlist check LIST [--online]    # lint the list; --online verifies arXiv ids
```

Every command accepts `--section S` (a ranking section), `--group G`, `--tag T`
and `--out DIR` (default: `papers/` next to the list).

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
