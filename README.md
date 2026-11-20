# readlist

Keep a reading list in git. Fetch the open-access PDFs locally.

```
$ readlist fetch reading-list.yaml
  [x] got    costan2016sgx   pdf link in list
  [x] got    lee2020keystone arxiv 1907.10119
  [x] got    xu2015controlled semantic scholar
  [~] manual li2024sok       papers/01-map/01-li2024sok.url
  [x] have   yu2023capstone  papers/05-angle/01-yu2023capstone.pdf

5 papers: 0 failed, 1 need a manual fetch (see the .url files in papers).
```

A lab, a course or a group of co-authors commits one list file. Everyone runs
`readlist fetch` and gets the same folder of PDFs on their own machine. The
PDFs never enter the repository, because they are copyrighted.

## Why not just Zotero?

Use Zotero for your personal library. readlist is for a *shared, ordered* list:

- **The list is a file you review like code.** Reading order, groups, "why
  read this" notes and tags all show up as diffs.
- **Annotation-safe.** A PDF you already have is never downloaded again.
  Each download is checksummed. If `--force` would replace a file you have
  highlighted, the annotated copy is moved to `annotated-backup/` first.
- **Verified, not guessed.** An arXiv id is checked against the paper's title
  before anything is saved, so a wrong id is reported, not silently
  downloaded as the wrong paper.
- **Honest about gaps.** A paper with no open copy gets a `.url` file that
  opens its landing page with a double-click, so you fetch it by hand.

## Install

```
uv tool install git+https://github.com/biecho/readlist
# or: pipx install git+https://github.com/biecho/readlist
```

Requires Python 3.11 or newer. The only dependency is PyYAML.

## Lists

### YAML

```yaml
groups:                         # `stages:` also works
  - id: 01-map
    title: Get the map
    papers:
      - id: costan2016sgx
        title: Intel SGX Explained
        tags: [core]            # select with --tag core
        pdf: https://css.csail.mit.edu/6.858/2019/readings/costan-sgx.pdf
      - id: lee2020keystone
        title: "Keystone: An Open Framework for Architecting Trusted Execution Environments"
        arxiv: "1907.10119"     # quote it: YAML turns 2010.08440 into 2010.0844
```

Files land in `papers/<group>/<NN>-<id>.pdf`, where NN is the paper's
position in its group. Other fields: `authors`, `year`, `venue`, `doi`,
`landing`, `kind` (`talk` and `web` always get a link placeholder rather than a
download), and `open_copy: false`, which means only an explicit `pdf` link
counts. Any other keys, such as your own reading notes, are ignored, so keep
them in the list. See [`examples/reading-list.yaml`](examples/reading-list.yaml).

### BibTeX

```
readlist fetch refs.bib                              # every entry
readlist fetch refs.bib --bbl build/main.bbl         # cited entries, numbered as in the paper
readlist fetch refs.bib --groups reading-list.csv    # one folder per group
```

readlist uses `pdfurl` (a non-standard field that BibTeX styles ignore), `url`
when it ends in `.pdf`, `eprint` (arXiv) and `doi`. `opencopy = {none}` marks
an entry whose only open copy is a different version, such as a superseded
preprint. An entry with only a non-PDF `url` is treated as a web resource.

### CSV

One row per paper: `id`, `title`, plus any of `group`, `authors`, `year`,
`venue`, `tags` (separated by `;`), `pdf`, `arxiv`, `doi`, `landing`, `kind`.

## Where PDFs come from

For each paper, readlist tries these in order and stops at the first hit:

1. A `pdf` link written in the list. A link you found by hand always wins.
2. The `arxiv` id, after checking it against the title.
3. [Unpaywall](https://unpaywall.org) by DOI. This needs a contact email; see Configuration.
4. [Semantic Scholar](https://www.semanticscholar.org), by DOI or by title.
   Results are title-checked, and DOI links (publisher landing pages) are ignored.
5. An arXiv search by title, as a last resort.

Pass `--record` and any link found by steps 3–5 is written back into the list
file. Only that one line changes; comments and formatting stay. Your
collaborators then get the link without a lookup.

readlist fetches open copies only. It does not scrape publishers, drive
institutional proxies or use shadow libraries, and that will not change.
Paywalled papers are one authenticated click away; that is what the `.url`
files are for.

## Commands

```
readlist fetch  LIST [--dry-run] [--force] [--record]
readlist list   LIST                 # [x] have  [~] manual  [ ] not yet
readlist check  LIST [--online]      # lint; --online verifies every arXiv id
```

Common options: `--group G`, `--tag T`, `--out DIR` (default: `papers/` next
to the list), `--bbl FILE`, `--groups CSV`.

## Configuration

`~/.config/readlist/config.toml`:

```toml
email = "you@example.org"        # enables Unpaywall
semantic_scholar_key = "..."     # optional private quota
```

The environment variables `READLIST_EMAIL` and `S2_API_KEY` override the
file. These settings stay with each user and never go into a shared list.

## Being polite

readlist identifies itself in its User-Agent and waits between requests to
the same host: 3 seconds for arXiv, as arXiv asks, and 1 second elsewhere. It
backs off when a server answers HTTP 429.

## License

MIT
