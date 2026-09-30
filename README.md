# Preprint Radar

A friendlier way to browse and search recent arXiv papers for literature reviews.

A Python pipeline collects the papers announced every day in one or more arXiv
categories — with abstracts and author affiliations — and a static web app hosted on
GitHub Pages lets anyone search them by keyword, author or affiliation, and keep a
reading list exported as BibTeX.

```
            GitHub Actions (weekdays)                        GitHub Pages
┌────────────────────────────────────────────────┐   ┌────────────────────────────┐
│ preprint-radar update                          │   │ web/ (Preact + MiniSearch) │
│   listing       arxiv.org/list/<cat>/recent    │   │  - full-text search        │
│   abstracts     rss.arxiv.org, API, HTML       │──▶│  - author / affiliation    │
│   affiliations  arxiv.org/html/<id>            │   │    filters and facets      │
│ → data/<cat>/<date>.json + data/index.json     │   │  - reading list, BibTeX    │
└────────────────────────────────────────────────┘   └────────────────────────────┘
```

## Where the data comes from

| Field                         | Source                                                                 |
| ----------------------------- | ---------------------------------------------------------------------- |
| Title, authors, subjects, comments, links | `https://arxiv.org/list/<category>/recent` (last 5 announcement days); `https://arxiv.org/catchup/<category>/<date>` for older days |
| Abstract                      | The category RSS feed (latest day, one request), then the catchup page of each older day (one request per day); the arXiv API and the paper's HTML rendering as last resorts |
| Affiliations                  | Submitter-declared affiliations from the API when present; otherwise the front matter of the paper's HTML rendering |
| Institution of each affiliation | The [Research Organization Registry](https://ror.org) (ROR) affiliation matching, when confident; otherwise the web app's own rules (acronyms, companies, departments) |
| Citations (archive)           | [Semantic Scholar](https://www.semanticscholar.org) citation counts, weekly; papers older than 12 months from arXiv's OAI-PMH, with affiliations from [OpenAlex](https://openalex.org) |
| Venue                         | Detected in the comments and journal reference ("Accepted to ECCV 2026", "BMVC2026", …); submissions and papers under review are ignored |

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
only once. `PREPRINT_RADAR_CONTACT` (an e-mail address or URL) is sent to arXiv in the
User-Agent so they can reach whoever runs the crawler: put it in a local `.env` file (see
`.env.example`, read by the Makefile) and in a repository variable on GitHub.

## Requirements

- [uv](https://docs.astral.sh/uv/) for the Python pipeline
- Node.js 24+ for the web app

## Usage

```bash
uv sync
uv run preprint-radar update                       # cs.CV into data/ (slow: reads HTML pages)
uv run preprint-radar update -c cs.CV -c cs.LG --max-html 50
uv run preprint-radar backfill --since 2026-09-01  # past days, from arXiv's catchup pages
uv run preprint-radar fetch --latest-only -f csv   # quick one-off export of the listing

cd web
npm install
npm run dev                                      # http://localhost:5173, serves ../data
```

In the web app, the search box supports prefix and typo-tolerant matching,
`"exact phrases"` and `-exclusions`, over titles, abstracts, authors, affiliations and
comments. The *Period* calendar picks the latest days, one day or a range of days (it shows
how many papers each day has). The *Author* and *Affiliation* fields filter by name (partial,
case- and accent-insensitive, with suggestions); clicking a name on a paper fills them.
The *Venue* filter keeps the papers accepted at one venue, or at any (major venues first, then alphabetically). With search
words, results are sorted by relevance: MiniSearch's BM25 score, where rarer words weigh
more and matches count most in the title (×3), then authors (×2), affiliations (×1.5),
abstract (×1) and comments (×0.5). Without search words (or sorted by newest), the papers
of each announcement day fold under a heading. Searches are encoded in the URL, so they
can be shared;
*Share* on a paper copies a link that opens that paper alone, expanded, on its announcement
day, and *Graph* opens the graph centered on it, with its details. The ◐ button next to
the tabs switches between the automatic, light and dark themes.

The *Graph* tab is a full-screen map of the loaded papers, their institutions and
(optionally) their authors. By default it shows papers (squares) linked to their
institutions; with authors on, a paper links to its authors, and an institution to the
authors the paper places there. Without papers, it becomes a collaboration map: institutions
and authors linked when they appear on the same paper. Variants of an institution's name are
merged approximately ("Google, Switzerland" and "Google", "CMU" and "Carnegie Mellon
University", "Microsoft Research Asia" and "Microsoft"); a department or an address on its
own makes no node. Drag, scroll to zoom, click a
node to see its details, double-click it to list its papers (or open the paper). The
*Graph settings* panel chooses the period (same calendar), restricts the graph to papers
matching some words, highlights nodes by name or title (`/`), shows or hides papers,
institutions, authors and isolated nodes, sets a minimum number of papers per institution
or author or a maximum number of them (all by default), tunes the forces and labels, and
replays how the graph grew day by day. An institution's or author's area grows with its
number of papers. Settings are remembered in the browser.

`backfill` collects past days (weekends are skipped quickly) and saves each day with its
abstracts before reading the HTML pages for affiliations, most recent day first; stopping
it loses nothing, and running it again resumes where it stopped. A month of cs.CV is about
2,900 papers: a few minutes for the days, then about 11 hours of HTML pages.

`archive` (weekly in CI) keeps the papers that matter beyond the last 12 months. It ranks
every cs.CV paper since 2010 by citations per year of age — fair to old and recent papers
alike — and keeps a budget of them (22,000 by default, about 20 citations a year today) in
`data/<category>/archive/<year>.json`. The threshold rises by itself as the field grows; a
paper leaves only once it ranks beyond 1.15 times the budget, and a paper that takes off
later comes back. Deleting the day files older than 12 months is off until you turn it on
(`--prune`, or the `PREPRINT_RADAR_ARCHIVE_PRUNE` repository variable). Citation counts are
much faster with a free Semantic Scholar API key, set as the `SEMANTIC_SCHOLAR_API_KEY`
repository secret.

## Deployment on GitHub Pages

1. Push the repository to GitHub.
2. In *Settings → Pages*, set *Source* to **GitHub Actions**.
3. In *Settings → Secrets and variables → Actions → Variables*, optionally set:
   - `PREPRINT_RADAR_CATEGORIES`: space-separated categories (default: `cs.CV`);
   - `PREPRINT_RADAR_CONTACT`: your e-mail address, sent to arXiv in the User-Agent
     (default: the repository URL).
4. Run the *Update data* workflow once by hand (*Actions → Update data → Run workflow*).
   A first run over the five days of the listing reads ~750 HTML pages and takes about
   3 hours; daily runs then take ~40 minutes. To collect older days, or days missed while
   the workflow was not running, fill its *since* field (YYYY-MM-DD): it then runs
   `backfill`, limited like any run to *max-html* HTML pages (run it again to go on).

The *Update data* workflow then runs every weekday, commits the new data and redeploys
the site. The *Deploy site* workflow also runs on every push touching `web/` or `data/`.

## Project layout

```
src/preprint_radar/
├── cli.py          # `preprint-radar` command (fetch, update, backfill)
├── pipeline.py     # update (recent listing) and backfill (catchup pages) → enrichment → store
├── listing.py      # /list/<category>/recent and /catchup/<category>/<date> pages
├── rss.py          # abstracts from the RSS feed
├── arxiv_api.py    # abstracts and declared affiliations from the Atom API
├── paper_page.py   # affiliations and abstract from HTML renderings
├── venue.py        # accepted venue detected from comments
├── store.py        # data/ layout read by the web app
├── stats.py        # enrichment coverage report over the store
├── http.py         # rate-limited HTTP client with retries
├── models.py       # Paper, Listing
├── filters.py      # helpers to narrow down papers
├── export.py       # JSON / CSV export
└── exceptions.py
web/
├── src/            # Preact app: search.ts (MiniSearch), graph.ts + graph-renderer.ts, hooks/, components/, …
└── tests/          # Vitest unit tests
data/               # generated by the pipeline, committed and published
tests/              # pytest: unit (offline, fixtures) and integration (network)
```

## Development

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
make stats       # how much of data/ is enriched, per day
make institutions # name the institutions of stored affiliations through ROR
make archive     # keep the most cited older papers (weekly in CI; first run about 2 h)
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
uv run pre-commit run --all-files
```

If arXiv changes its page layout, the network test fails first: refresh the fixtures in
`tests/fixtures/` from live pages and update the parsers.

Thank you to arXiv for use of its open access interoperability. This project is not
affiliated with arXiv.
