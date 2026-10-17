# <picture><source media="(prefers-color-scheme: dark)" srcset="web/public/preprint-radar-lockup-dark.svg"><img src="web/public/preprint-radar-lockup-light.svg" alt="Preprint Radar" height="40"></picture>

Follow and search the cs.CV papers announced on arXiv every weekday, with their affiliations, citations and the most cited older papers.

**The site:** <https://titouanlegourrierec.github.io/preprint-radar/>

A Python pipeline, run by GitHub Actions, collects the papers announced every weekday in
one or more arXiv categories, with their abstracts, affiliations and citation counts, and
keeps the most cited older papers. It commits them to `data/`, which a static web app on
GitHub Pages searches: there is no server.

```
                  GitHub Actions                              GitHub Pages
┌────────────────────────────────────────────────┐   ┌────────────────────────────┐
│ update (weekdays)                              │   │ web/ (Preact + MiniSearch) │
│   listing       arxiv.org/list/<cat>/recent    │   │  - full-text search        │
│   abstracts     rss.arxiv.org, catchup, API    │   │  - author, institution,    │
│   affiliations  arxiv.org/html/<id>, OpenAlex  │   │    venue and code filters  │
│   institutions  ror.org                        │──▶│  - highly cited papers     │
│   citations     Semantic Scholar               │   │  - rankings, world map     │
│ archive (Sundays)                              │   │  - graph, Atom feeds       │
│   older papers  OAI-PMH, Semantic Scholar      │   │  - reading list, folders   │
│   affiliations  OpenAlex                       │   │                            │
│   stars         GitHub, Hugging Face           │   │                            │
│ → data/<cat>/<date>.json, archive/<year>.json, │   │                            │
│   citations.json, scholar.json, index.json     │   │                            │
└────────────────────────────────────────────────┘   └────────────────────────────┘
```

## What the site does

- **Papers**: the latest announcement day, the last week or month, or any period of the
  calendar, searched as you type (word prefixes, a typo, `"phrases"`, `-exclusions`) over
  titles, abstracts, authors, affiliations, venues and comments, and filtered by author,
  institution, venue, subject or code. A search is a link to share.
- **Highly cited**: the most cited papers of each year since 2010, and of the last 12
  months, ranked by citations or by those gained this week.
- **Rankings**: the institutions, authors or countries of the papers shown, by papers or
  citations, with a world map of the countries, flat or on a globe.
- **Graph**: the papers, their institutions and authors, or who works with whom, replayed
  day by day; saved as PNG or GraphML.
- **Reading list**: the papers you star, in folders, exported as BibTeX, RIS, CSV or
  Markdown; a folder is shared by a link. It stays in your browser.
- **Feeds**: an Atom feed of every institution of the recent papers, and of each major
  venue.

Each view explains itself (its ⓘ notes, the About page); [`docs/web.md`](docs/web.md) says
how it works.

## Where the data comes from

| Field                         | Source                                                                 |
| ----------------------------- | ---------------------------------------------------------------------- |
| Title, authors, subjects, comments, links | `https://arxiv.org/list/<category>/recent` (last 5 announcement days); `https://arxiv.org/catchup/<category>/<date>` for older days |
| Abstract                      | The category RSS feed (latest day, one request), then the catchup page of each older day (one request per day); the arXiv API and the paper's HTML rendering as last resorts |
| Affiliations                  | Submitter-declared affiliations from the API when present; otherwise the front matter of the paper's HTML rendering; for the 5% arXiv has no HTML rendering of, [OpenAlex](https://openalex.org) |
| Institution of each affiliation | The [Research Organization Registry](https://ror.org) (ROR) affiliation matching, when confident; otherwise the pipeline's own rules (acronyms, companies, the main part of an address) |
| Citation counts (every stored paper) | [Semantic Scholar](https://www.semanticscholar.org), weekly (new papers the day they are added); the archive's papers, older than 12 months, and the most cited of the last 12 months that no day file holds, from arXiv's OAI-PMH, with affiliations from [OpenAlex](https://openalex.org): its record of the preprint, else of the published version, else the paper's HTML rendering |
| Venue                         | Detected in the comments and journal reference ("Accepted to ECCV 2026", "BMVC2026", …); submissions and papers under review are ignored. Else where Semantic Scholar says it was published, with its DOI |
| Code and its stars            | The first GitHub or GitLab repository the abstract or comments link, else its models, data or demo on Hugging Face; the repository's [GitHub](https://github.com) stars (the page's Hugging Face likes), weekly (new papers the next weekday), with those gained in the week. A repository other stored papers link too, or a folder of a larger one, is marked shared |

Affiliations are **best effort**: arXiv's metadata rarely has them, so they are read from
the front matter of each paper's HTML rendering, whose layout depends on its LaTeX class
([`docs/extraction.md`](docs/extraction.md) lists the layouts read, each from a real page).
Where the page says who is where, each author is mapped to their own affiliations. About
one paper in five still has none.

The pipeline is deliberately polite: one request every 15 s to arxiv.org (its
`robots.txt` crawl delay), a few seconds between API calls, and each paper is enriched
only once. `PREPRINT_RADAR_CONTACT` (an e-mail address or URL) is sent to arXiv (its
pages, API and OAI-PMH, never the other services) in the User-Agent so they can reach
whoever runs the crawler: put it in a local `.env` file (see `.env.example`, read by the
Makefile) and in a repository variable on GitHub.

## Why `data/` is in git

The data is files the site serves as they are: GitHub Pages hosts them beside the app, with
no server or database to run or pay for, and the workflows publish a day's papers by
committing them. Git then keeps every version of every record: a change of the extraction
or a bad run shows as a diff of `data/` and is undone by a commit, and `validate` checks
the whole store before every data commit and on every other push. The cost is a repository
that grows by about 110 MB of day files a year of cs.CV, mostly history, which a partial
clone skips ([Development](#development)); pruning keeps a rolling year of day files, and
[`docs/operations.md`](docs/operations.md#the-site-or-the-repository-grows-too-large) says
when and how the store would leave `main`. This choice and the others are logged in the
roadmap's [Decisions](docs/roadmap.md#decisions) table.

## Usage

Requirements: [uv](https://docs.astral.sh/uv/) for the pipeline, Node.js 24+ for the site.

```bash
uv sync
uv run preprint-radar update                       # cs.CV into data/ (slow: up to 600 HTML pages)
uv run preprint-radar update -c cs.CV -c cs.LG --max-html 50
uv run preprint-radar backfill --since 2026-09-01  # past days, from arXiv's catchup pages
uv run preprint-radar archive                      # the most cited older papers (weekly in CI)
uv run preprint-radar --help                       # every command; -q for warnings only

cd web
npm install
npm run dev                                      # http://localhost:5173, serves ../data
```

`update` and `backfill` read at most 600 HTML pages a run, one every 15 s: about 2.5 hours
(`--max-html` changes it). Stopping one loses nothing, and running it again resumes. A
month of past cs.CV days is about 2,900 papers: minutes for the days, then about 11 hours
of pages.

`archive` keeps the papers that matter beyond the last 12 months: each week it ranks every
paper of the category since 2010 by citations per year of age and keeps a budget of them
(22,000 by default, about 20 citations a year), so that a paper that takes off later comes
in ([`docs/archive.md`](docs/archive.md) has the calibration behind it). A free Semantic
Scholar API key (`SEMANTIC_SCHOLAR_API_KEY`) makes it much faster.

## Deployment on GitHub Pages

The site is public, and so is all of `data/`, which it serves: GitHub Pages publishes a
site to anyone even from a private repository (only GitHub Enterprise Cloud can restrict
it to members). A fork that deploys it republishes the data, authors and affiliations
included, under its own address. A GitHub fork never runs the data workflows on
schedule, so that turning its Actions on does not crawl arXiv daily: only runs started by
hand or dispatched (step 6) go on. For daily runs on schedule, push a copy instead
(step 1).

1. Push the repository to GitHub.
2. In *Settings → Pages*, set *Source* to **GitHub Actions**.
3. In *Settings → Secrets and variables → Actions → Variables*, optionally set:
   - `PREPRINT_RADAR_CATEGORIES`: space-separated categories (default: `cs.CV`);
   - `PREPRINT_RADAR_CONTACT`: your e-mail address, sent to arXiv in the User-Agent
     (default: the repository URL);
   - `PREPRINT_RADAR_ARCHIVE_BUDGET`: how many papers older than 12 months the archive
     keeps per category (default: 22000);
   - `PREPRINT_RADAR_ARCHIVE_PRUNE`: `true` to delete the day files older than 12 months,
     for a rolling year of them (default: `false`; this repository sets it).

   Under *Secrets*, optionally set `SEMANTIC_SCHOLAR_API_KEY`, a free
   [Semantic Scholar API key](https://www.semanticscholar.org/product/api): without it,
   citation counts are asked for anonymously, and the weekly archive takes hours instead of
   about 40 minutes.
4. Run the *Update data* workflow once by hand (*Actions → Update data → Run workflow*).
   A first run over the five days of the listing (about 750 papers) reads at most 600 HTML
   pages, the pipeline's default (*max-html* changes it), in about 2.5 hours; the next runs
   read the rest, and daily runs then take ~40 minutes. To collect older days, or days
   missed while the workflow was not running, fill its *since* field (YYYY-MM-DD): it then
   runs `backfill`, limited like any run to 600 HTML pages (run it again to go on).
5. Run the *Archive* workflow once by hand too (*Actions → Archive → Run workflow*), or
   *Highly cited* stays empty until the first Sunday. Its first run harvests arXiv's
   catalog (about 45 minutes) before asking for the citation counts (about 40 minutes with
   the key, hours without); it waits for a running *Update data*, since the two never
   commit at the same time.
6. For runs on time, have an outside scheduler dispatch both workflows: GitHub starts
   scheduled runs hours late, so their own schedules are only fallbacks, four hours after
   the dispatch times. [`docs/operations.md`](docs/operations.md#the-outside-scheduler)
   sets it up with cron-job.org; without it, the fallbacks still run, late.

The *Update data* workflow then runs every weekday and *Archive* every Sunday; each commits
the new data and redeploys the site. The *Deploy site* workflow also runs on every push
touching `web/` or `data/`, after the web tests.

When a run is red, late or missing, or the archive did not change, see
[`docs/operations.md`](docs/operations.md): one section per symptom, starting from what
the run's page says, and how long each task takes.

## Project layout

```
src/preprint_radar/
├── cli.py              # `preprint-radar` command (update, backfill, archive, citations, scholar, validate, stats…)
├── collect.py          # update, backfill, reextract → enrichment → store; citation and scholar steps
├── config.py           # tunable defaults: category, directories, HTML pages per run, archive budget and policy
├── venue.py            # venue table: venues detected from comments, and Semantic Scholar's named alike
├── models.py           # Paper, Listing, ScholarRecord, Institution
├── http.py             # rate-limited HTTP client with retries
├── console.py          # terminal output: rich in a terminal, plain text in CI and pipes
├── exceptions.py
├── sources/            # one module per external service
│   ├── arxiv_listing.py    # /list/<category>/recent and /catchup/<category>/<date> pages
│   ├── arxiv_rss.py        # abstracts from the RSS feed
│   ├── arxiv_api.py        # abstracts and declared affiliations from the Atom API
│   ├── arxiv_html.py       # affiliations and abstract from HTML renderings
│   ├── arxiv_oai.py        # bulk metadata harvest (OAI-PMH)
│   ├── semantic_scholar.py # citation counts, DOIs, published venues, author ids
│   ├── openalex.py         # institutions of archived papers
│   ├── github.py           # stars of the code papers link
│   ├── huggingface.py      # likes of their Hugging Face pages
│   └── ror.py              # institution named by an affiliation string
├── archive/            # weekly citation archive: catalog, selection, update
└── store/              # data/ layout, validate, stats, quality, reclean, venues, naming
web/
├── src/            # Preact app: search.ts (MiniSearch), graph.ts + graph-renderer.ts, hooks/, components/, …
├── tooling/        # build plugins: citation shards, published versions, third-party guard
├── tests/          # Vitest unit tests
└── e2e/            # Playwright smoke test of the built site, over its own small store
data/               # generated by the pipeline, committed and published
tests/              # pytest: unit (offline, fixtures) and integration (network)
docs/               # operations (runbook), extraction, archive, web, roadmap, audit
```

## Development

Most of the history is past versions of `data/`: a partial clone,
`git clone --filter=blob:none <url>`, downloads the files of the commit checked out, and
past versions only when a command such as `git log -p` needs them.

The `Makefile` wraps the usual commands (`make` lists them):

```bash
make install     # Python + web dependencies, git hooks
cp .env.example .env   # then set PREPRINT_RADAR_CONTACT
make format      # auto-format and fix Python and web code
make quality     # every quality check: formatting, lint, types (Python, web, workflows)
make check       # quality checks and all tests, as CI does
make dev         # web app with hot reload on http://localhost:5173
make preview     # production build of the site, served locally
make update      # refresh data/ (CATEGORIES="cs.CV cs.LG" MAX_HTML=50)
make backfill SINCE=2026-09-01   # add past days to data/ (UNTIL defaults to today)
make stats       # how much of data/ is enriched, per day and per archive year
make institutions # name the institutions of stored affiliations through ROR
make citations   # citation counts of the papers added since the weekly archive (ALL=1: every paper)
make archive     # keep the most cited older papers (weekly in CI; first run about 2 h)
make archive-affiliations   # affiliations of highly cited papers from their published version (MAX_HTML=N: their HTML pages too)
make code        # GitHub stars of the code papers link (GITHUB_TOKEN in .env; weekly in CI, NEW=1 daily)
```

`make test-network` runs the parsers against the live arXiv (slow, polite).

If arXiv changes its page layout, the network test fails first (the weekly *arXiv canary*
workflow runs it): refresh the fixtures in `tests/fixtures/` from live pages and update the
parsers. A daily run that finds nearly every page without affiliations stops and goes red,
leaving those papers pending ([`docs/operations.md`](docs/operations.md) has the steps).

## Licenses

The code is under the [MIT license](LICENSE). The data in `data/` is not: it is collected
from services that set their own terms.

- Paper metadata (titles, authors, abstracts, comments) comes from arXiv, whose metadata is
  under [CC0](https://info.arxiv.org/help/api/tou.html). Each paper itself keeps the license
  its authors chose on arXiv.
- Institution names come from [ROR](https://ror.org) and [OpenAlex](https://openalex.org),
  both under CC0.
- Citation counts come from the [Semantic Scholar API](https://www.semanticscholar.org/product/api),
  under its license agreement.

Thank you to arXiv for use of its open access interoperability. This project is not
affiliated with arXiv.
