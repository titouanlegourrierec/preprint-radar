# Development

## Setup

Requirements: [uv](https://docs.astral.sh/uv/) for the pipeline (Python 3.13+), Node.js 24+
for the site.

```bash
git clone --filter=blob:none https://github.com/titouanlegourrierec/preprint-radar.git
cd preprint-radar
make install            # Python and web dependencies, git hooks
cp .env.example .env    # then set PREPRINT_RADAR_CONTACT
make dev                # the site on http://localhost:5173, over ../data
```

Most of the history is past versions of `data/`: the partial clone above downloads the
files of the commit checked out, and past versions only when a command needs them.

## Everyday commands

`make help` lists every target.

| Command | What it does |
|---|---|
| `make check` | What CI runs: formatting, lint and types (Python, web, workflows), then every offline test. Run it before saying a change is done |
| `make format` | Format and auto-fix Python and web code |
| `make coverage` | Python coverage; CI fails below 95%, the project keeps 100% |
| `make test-e2e` | The Playwright smoke test of the built site, over `web/e2e/data` |
| `make test-network` | The parsers against the live arXiv (slow) |
| `make preview` | The production build of the site, served locally |

A single test: `uv run pytest tests/unit/test_paper_store.py -k merge`, or
`cd web && npx vitest run tests/search.test.ts`.

## Running the pipeline

The commands write into `data/`; `uv run preprint-radar --help` describes each.

| Command | Duration |
|---|---|
| `make update` | The recent days, with up to 600 HTML pages at one every 15 s: up to 2.5 hours (`MAX_HTML=N`) |
| `make update-quick` | The same without the pages: a few minutes |
| `make backfill SINCE=YYYY-MM-DD` | Past days from arXiv's catchup pages, then their pages, 600 a run |
| `make archive` | The weekly citation archive: about 40 minutes with a Semantic Scholar key, hours without; the first run harvests the catalog (45 minutes) |
| `make citations`, `scholar`, `code`, `countries`, `affiliations` | One enrichment each, seconds to minutes |
| `make trends` | The topics of the titles, offline, under a minute |
| `make validate`, `make stats` | Check `data/` against its contract; how much of it is enriched |

Stopping a run loses nothing, and running it again resumes. Keys go in `.env`, read by the
Makefile: `SEMANTIC_SCHOLAR_API_KEY` for the counts, `GITHUB_TOKEN` for `make code`.

## Tests

Tests are offline: HTTP is mocked, and a test that reaches the network fails. The fixtures
under `tests/fixtures/` are trimmed copies of real arXiv pages, their e-mail addresses
replaced; `tests/fixtures/html/expected.json` pins what each page gives. Live tests are in
`tests/integration/`, marked `network`, and run weekly by the *arXiv canary* workflow, which
is the first to fail when arXiv changes its pages.

## Conventions

- Everything in the repository is in English.
- Python is fully typed, with Google-style docstrings; Ruff runs every rule and ty checks
  the types. The web app is strict TypeScript, checked by Biome, with Preact hooks and no
  CSS framework; colors are the variables of `styles.css`, in light and dark.
- HTTP goes through `http.HttpClient` (rate limits, retries), output through `console.py`,
  and errors subclass `PreprintRadarError`, which the CLI turns into a log line.
- The paper record is `Paper` in `models.py`, mirrored in `web/src/types.ts`; a test
  compares them. [data-format.md](data-format.md) says how the format may change.
- Commits are small and conventional, naming the roadmap item they change:
  `fix(collect): … (DATA-2)`, with its status in [roadmap.md](roadmap.md) and, when users
  would notice it, an entry under `## Unreleased` in `CHANGELOG.md`.
