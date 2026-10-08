# Preprint Radar

A friendlier way to browse and search recent arXiv papers for literature reviews.

A Python pipeline collects the papers announced every day in one or more arXiv
categories — with abstracts and author affiliations — and a static web app hosted on
GitHub Pages lets anyone search them by keyword, author or affiliation, and keep a
reading list exported as BibTeX, RIS, CSV or Markdown.

```
                  GitHub Actions                              GitHub Pages
┌────────────────────────────────────────────────┐   ┌────────────────────────────┐
│ update (weekdays)                              │   │ web/ (Preact + MiniSearch) │
│   listing       arxiv.org/list/<cat>/recent    │   │  - full-text search        │
│   abstracts     rss.arxiv.org, catchup, API    │   │  - author / affiliation    │
│   affiliations  arxiv.org/html/<id>            │   │    and venue filters       │
│   institutions  ror.org                        │──▶│  - highly cited, rankings  │
│   citations     Semantic Scholar               │   │  - graph, Atom feeds       │
│ archive (Sundays)                              │   │  - reading list, BibTeX    │
│   older papers  OAI-PMH, Semantic Scholar      │   │                            │
│   affiliations  OpenAlex                       │   │                            │
│ → data/<cat>/<date>.json, archive/<year>.json, │   │                            │
│   citations.json, scholar.json, index.json     │   │                            │
└────────────────────────────────────────────────┘   └────────────────────────────┘
```

## Where the data comes from

| Field                         | Source                                                                 |
| ----------------------------- | ---------------------------------------------------------------------- |
| Title, authors, subjects, comments, links | `https://arxiv.org/list/<category>/recent` (last 5 announcement days); `https://arxiv.org/catchup/<category>/<date>` for older days |
| Abstract                      | The category RSS feed (latest day, one request), then the catchup page of each older day (one request per day); the arXiv API and the paper's HTML rendering as last resorts |
| Affiliations                  | Submitter-declared affiliations from the API when present; otherwise the front matter of the paper's HTML rendering; for the 5% arXiv has no HTML rendering of, [OpenAlex](https://openalex.org) |
| Institution of each affiliation | The [Research Organization Registry](https://ror.org) (ROR) affiliation matching, when confident; otherwise the pipeline's own rules (acronyms, companies, the main part of an address) |
| Citation counts (every stored paper) | [Semantic Scholar](https://www.semanticscholar.org), weekly (new papers the day they are added); the archive's papers, older than 12 months, and the most cited of the last 12 months that no day file holds, from arXiv's OAI-PMH, with affiliations from [OpenAlex](https://openalex.org): its record of the preprint, else of the published version, else the paper's HTML rendering |
| Venue                         | Detected in the comments and journal reference ("Accepted to ECCV 2026", "BMVC2026", …); submissions and papers under review are ignored. Else where Semantic Scholar says it was published, with its DOI |

Affiliations are **best effort**: arXiv metadata rarely includes them, and the HTML
front matter depends on each paper's LaTeX class. They are read from the affiliation and
address fields of the author block, the address and institute notes of Elsevier-, IEEE- or
Springer-like classes, numbered footnotes next to the author list, numbered lines after the
names, and IEEE-style notes ("A and B are with the University of X"). They are extracted with
contact details removed, and, when the page says who is where (one block per author,
superscript markers, "A is with B" notes), each author is also mapped to their own
affiliations — the graph then links an author only to their institutions. Some papers
still have none: the LaTeX class may put affiliations where LaTeXML drops them, and papers
without an HTML rendering (~6%) cannot be read.

The pipeline is deliberately polite: one request every 15 s to arxiv.org (its
`robots.txt` crawl delay), a few seconds between API calls, and each paper is enriched
only once. `PREPRINT_RADAR_CONTACT` (an e-mail address or URL) is sent to arXiv (its
pages, API and OAI-PMH, never the other services) in the User-Agent so they can reach
whoever runs the crawler: put it in a local `.env` file (see `.env.example`, read by the
Makefile) and in a repository variable on GitHub.

## Requirements

- [uv](https://docs.astral.sh/uv/) for the Python pipeline
- Node.js 24+ for the web app

## Usage

```bash
uv sync
uv run preprint-radar update                       # cs.CV into data/ (slow: up to 600 HTML pages)
uv run preprint-radar update -c cs.CV -c cs.LG --max-html 50
uv run preprint-radar backfill --since 2026-09-01  # past days, from arXiv's catchup pages
uv run preprint-radar fetch --latest-only -f csv   # quick one-off export of the listing
uv run preprint-radar -q update                    # warnings only (long commands log progress)

cd web
npm install
npm run dev                                      # http://localhost:5173, serves ../data
```

In the web app, the search box supports prefix and typo-tolerant matching,
`"exact phrases"` and `-exclusions`, over titles, abstracts, authors, affiliations and
comments. The *Period* calendar picks the latest days, one day or a range of days (it shows
how many papers each day has). The *Author* and *Affiliation* fields filter by name (partial,
case- and accent-insensitive, with suggestions); clicking a name on a paper fills them.
The *Venue* filter keeps the papers accepted at one venue, every edition of one ("CVPR, any
year"), or any venue (major venues first, then alphabetically); *With code* keeps the papers
that link a repository (GitHub, GitLab) or models and data on Hugging Face. With search
words, results are sorted by relevance: MiniSearch's BM25 score, where rarer words weigh
more and matches count most in the title (×3), then authors (×2), affiliations (×1.5),
abstract (×1) and comments (×0.5). Without search words (or sorted by newest), the papers
of each announcement day fold under a heading. Searches are encoded in the URL, so they
can be shared;
*Share* on a paper copies a link that opens that paper alone, expanded, on its announcement
day, and *Graph* opens the graph centered on it, with its details. A card links its *Code*
when it has some, and, unfolded, its related work on Semantic Scholar, Connected Papers and
alphaXiv. The ◐ button next to
the tabs switches between the automatic, light and dark themes.

The *Highly cited* tab shows the archive by year of first version, one year, a range of
years or all of them, ranked by citation count, or the 1,000 most cited papers of the last
12 months, by citations per month of age; search words and filters narrow it down.
Past 10,000 papers (all years hold about 22,000), it keeps the best ranked by citations per
year of age and says how many it leaves out. Papers show their citation count wherever it
is known (0 for most new papers), and, once two weekly counts exist, what they gained in
the last week ("+12 this week"); the lists can be sorted by either (*Most cited*,
*Rising*).

The *Rankings* tab lists the institutions or the authors of the papers shown — the recent
days or archive years, narrowed by the search and filters — by number of papers or by
citations, with each one's most cited paper; a name opens its papers. "Who works on
gaussian splatting this month?" or "which labs wrote the most cited papers of 2017?".

The *Graph* tab is a full-screen map of the loaded papers (the recent days, or the highly
cited papers of some years, chosen under *From*), their institutions and
(optionally) their authors. By default it shows papers (squares) linked to their
institutions; with authors on, a paper links to its authors, and an institution to the
authors the paper places there. Without papers, it becomes a collaboration map: institutions
and authors linked when they appear on the same paper. Variants of an institution's name are
merged approximately ("Google, Switzerland" and "Google", "CMU" and "Carnegie Mellon
University", "Microsoft Research Asia" and "Microsoft"); a department or an address on its
own makes no node. Drag, scroll to zoom, click a
node to see its details (each of its connections lists the papers they share), double-click
it to list its papers (or open the paper); *Focus on this* shows the graph of a node's
papers alone, with whom an institution or an author publishes. The
*Graph settings* panel chooses the period (same calendar), restricts the graph to papers
matching some words, highlights nodes by name or title (`/`), shows or hides papers,
institutions, authors and isolated nodes, sets a minimum number of papers per institution
or author or a maximum number of them (all by default), tunes the forces and labels, and
replays how the graph grew day by day, and saves it as PNG or GraphML (for Gephi). An
institution's or author's area grows with its number of papers. Settings are remembered in
the browser.

Every institution of the recent papers, and each major venue, has an Atom feed of its
papers of the last 60 days (`feeds/<category>/…`, built with the site): a list filtered on
one links it, for a feed reader.

`backfill` collects past days (weekends are skipped quickly) and saves each day with its
abstracts before reading the HTML pages for affiliations, most recent day first; stopping
it loses nothing, and running it again resumes where it stopped. A day whose catchup page
fails, or comes back incomplete, is not saved: the others are read, the report names it and
the command exits with 1, and the next run fetches it again. A month of cs.CV is about
2,900 papers: a few minutes for the days, then about 11 hours of HTML pages. Like `update`,
it reads at most 600 HTML pages per category a run, 2.5 hours at one page every 15 s, which
fits the daily workflow's time limit (`DEFAULT_MAX_HTML` in `config.py`): run it again for
the rest, or raise the limit (`--max-html 3000`, `MAX_HTML=3000` with `make`).

`archive` (weekly in CI) keeps the papers that matter beyond the last 12 months. It ranks
every cs.CV paper since 2010 by citations per year of age — fair to old and recent papers
alike — and keeps a budget of them (22,000 by default, about 20 citations a year today) in
`data/<category>/archive/<year>.json`. The threshold rises by itself as the field grows; a
paper leaves only once it ranks beyond 1.15 times the budget, and a paper that takes off
later comes back. Deleting the day files older than 12 months, for a rolling year of them, is off until you
turn it on (`--prune`, or the `PREPRINT_RADAR_ARCHIVE_PRUNE` repository variable). Citation counts are
much faster with a free Semantic Scholar API key, set as the `SEMANTIC_SCHOLAR_API_KEY`
repository secret; a run that fails or is cancelled resumes from the counts it fetched.

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
│   └── ror.py              # institution named by an affiliation string
├── archive/            # weekly citation archive: catalog, selection, update
└── store/              # data/ layout, validate, stats, quality, reclean, venues, export, filters
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
```

The underlying commands:

```bash
# Python
uv run ruff format . && uv run ruff check --fix .
uv run ty check
uv run pytest --cov
uv run pytest -m network      # smoke test against the live arXiv (slow, polite)

# Web
cd web
npm run lint && npm run typecheck && npm test
npm run build                 # type-check + production build into web/dist (with data)

# Everything, as on commit
uv run prek run --all-files   # git hooks, with prek (a faster pre-commit)
```

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
