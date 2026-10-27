# How it works

Preprint Radar has three parts: a Python pipeline that collects papers, a store of JSON
files in `data/`, and a static web app that searches them. GitHub Actions runs the
pipeline and commits the store; GitHub Pages serves the store and the app. There is no
server.

```
                  GitHub Actions                              GitHub Pages
┌────────────────────────────────────────────────┐   ┌────────────────────────────┐
│ update (weekdays)                              │   │ web/ (Preact + MiniSearch) │
│   listing       arxiv.org/list/<cat>/recent    │   │  - full-text search        │
│   abstracts     rss.arxiv.org, catchup, API    │   │  - filters, rankings, map  │
│   affiliations  arxiv.org/html/<id>, OpenAlex  │──▶│  - highly cited papers     │
│   institutions  ror.org                        │   │  - trends of the topics    │
│   citations     Semantic Scholar               │   │  - graph, feeds            │
│ archive (Sundays)                              │   │  - reading list            │
│   older papers  OAI-PMH, Semantic Scholar      │   │                            │
│   affiliations  OpenAlex                       │   │                            │
│   stars         GitHub, Hugging Face           │   │                            │
│   trends        the catalog's titles           │   │                            │
│ → data/                                        │   │                            │
└────────────────────────────────────────────────┘   └────────────────────────────┘
```

## The pipeline

- **Every weekday** (`update.yml`): the day's listing, then each paper's abstract,
  affiliations (from its HTML rendering) and institutions, its citation count, the stars
  of the code it links and the countries of its institutions. Pages read by an older
  extraction are read again, a few dozen a day.
- **Every Sunday** (`archive.yml`): arXiv's catalog of the category since 2010, the
  citation counts of all of it, the most cited older papers kept in the archive, their
  published versions and affiliations, the stars of every paper's code, and the trends of
  the titles.

Every step saves as it goes and resumes where it stopped; a step that fails leaves the
others' data. [operations.md](operations.md) is the runbook.

## Where the data comes from

| Field | Source |
|---|---|
| Title, authors, subjects, comments | arXiv's listing (`/list/<category>/recent`, the last five announcement days), and its catchup pages for older days |
| Abstract | arXiv's RSS feed, then the catchup pages; the API and the HTML rendering as last resorts |
| Affiliations | The front matter of the paper's HTML rendering ([extraction.md](extraction.md)); [OpenAlex](https://openalex.org) for papers without one and for the archive |
| Institution | The [Research Organization Registry](https://ror.org) when it matches confidently, else the pipeline's own rules |
| Venue | The comments and journal reference ("Accepted to ECCV 2026"), else the published version [Semantic Scholar](https://www.semanticscholar.org) knows |
| Citations | Semantic Scholar, weekly, and daily for new papers ([archive.md](archive.md)) |
| Code | The first repository the abstract or comments link; its [GitHub](https://github.com) stars or [Hugging Face](https://huggingface.co) likes, weekly |
| Topics | The phrases of the catalog's titles since 2010 ([trends.md](trends.md)) |

Affiliations are best effort: arXiv's metadata rarely has them, and the front matter of a
rendering depends on its LaTeX class. About one paper in five has none.

The pipeline is polite: one request every 15 s to arxiv.org (its `robots.txt` crawl
delay), and each paper is enriched once. Requests to arXiv carry a contact
(`PREPRINT_RADAR_CONTACT`) in their User-Agent; other services never get it.

## Why `data/` is in git

The store is files that the site serves as they are, so there is no database to run or
pay for, and the workflows publish a day by committing it. Git keeps every version of
every record: a change of the extraction or a bad run shows as a diff and is undone by a
commit, and `make validate` checks the whole store before every data commit. The cost is
about 110 MB of day files a year of cs.CV, mostly history, which a partial clone skips;
the store keeps a rolling year of day files, older papers living on in the archive when
they are cited enough. [data-format.md](data-format.md) documents every file.

## Layout

```
src/preprint_radar/
├── cli.py          # the `preprint-radar` command
├── collect.py      # update, backfill, reextract, and the enrichment steps
├── steps.py        # an enrichment: which papers need it, and its run within a budget
├── models.py       # Paper and the records of every file
├── trends.py       # the topics of the titles
├── sources/        # one module per service: arXiv (listing, RSS, API, HTML, OAI-PMH),
│                   # Semantic Scholar, OpenAlex, ROR, GitHub, Hugging Face
├── archive/        # the weekly citation archive: catalog, selection, update
└── store/          # data/'s layout, validate, stats, cleaning and naming
web/
├── src/            # the Preact app
├── tooling/        # build plugins: what the site derives from data/, the third-party guard
├── tests/          # Vitest
└── e2e/            # Playwright smoke test over a small store of its own
data/               # the store, generated by the pipeline
tests/              # pytest: unit (offline, fixtures from real pages) and network tests
docs/               # this documentation
```
