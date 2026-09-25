# CLAUDE.md

Preprint Radar: a Python pipeline collects the papers announced daily on arXiv
(listing + abstracts + affiliations) into `data/`, and a static Preact app in `web/`
lets people search them. It is deployed on GitHub Pages; there is no server.

## Commands

Use the Makefile (`make help` lists everything):

- `make quality`: every static check (ruff format/lint, ty, Biome, tsc, actionlint). Run it before saying a change is done.
- `make test`: pytest and Vitest, both offline. `make check` runs quality and tests, like CI.
- `make format`: auto-fix formatting and lint.
- `make dev` / `make preview`: the site locally (dev server, or production build).
- `make update-quick`: refresh `data/` without reading HTML pages. `make update` reads them too, at one page every 15 s, so it takes hours. Never start it without asking.

Single checks: `uv run pytest tests/unit/test_store.py -k merge`, `cd web && npx vitest run tests/search.test.ts`.

## Layout

- `src/preprint_radar/`: `pipeline.py` orchestrates listing → abstracts → HTML front matter → store.
  - Sources: `listing.py`, `rss.py`, `arxiv_api.py`, `paper_page.py`.
  - HTTP goes through `http.HttpClient` only (rate limiting, retries, error mapping).
- `data/<category>/<YYYY-MM-DD>.json` + `data/index.json`: written by `store.py`, read by `web/src/data.ts`. Generated, but committed and deployed.
- `web/src/`: `search.ts` (MiniSearch index and query syntax), `app.tsx` (state), `components/`, `url-state.ts` (shareable URLs).
- `tests/fixtures/`: trimmed copies of real arXiv pages (listing, RSS, API feed, HTML front matter).

## Conventions

- Everything in the repo is in English: code, comments, docs, CLI help, commit messages.
- Python 3.13+, fully typed, Google-style docstrings on public functions.
  - Ruff runs with `select = ["ALL"]`: fix the code rather than adding `noqa`. Keep any `noqa` or `ty: ignore` rare, and justify it inline.
- Errors are subclasses of `exceptions.PreprintRadarError`. The CLI turns them into a log line and exit code 1, never a traceback.
- Tests are offline. Mock HTTP with `httpx.MockTransport` injected into `HttpClient`, or monkeypatch `HttpClient.get_text` for CLI tests. Tests that hit the real arXiv live in `tests/integration/` with the `network` marker, which is deselected by default.
- Web: TypeScript strict (TS 7), Biome for lint and format (no ESLint/Prettier), Preact hooks, no CSS framework. Theme colors come from the CSS variables in `styles.css`, with automatic light/dark.

## Data contract (keep both sides in sync)

- The paper record is defined by `Paper.to_record()` / `Paper.from_record()` in `models.py`, and mirrored in `web/src/types.ts`.
- A breaking change to the format means bumping `SCHEMA_VERSION` in both `store.py` and `types.ts`.
- `abstract` and `affiliations` use `null` for "not retrieved yet": the pipeline retries those.
- An empty list means "tried, nothing found"; the pipeline does not retry those.
- `affiliations` are per paper, deduplicated, and never contain e-mails or URLs.

## arXiv constraints (hard-won, do not "simplify" away)

- **arxiv.org:** `robots.txt` asks for a 15 s crawl delay. It is used for the listing, RSS and HTML pages (`ARXIV_CRAWL_DELAY_SECONDS`).
- **export.arxiv.org (the API):**
  - Its firewall returns an empty `406` to httpx's default header order and to `%2C`-encoded commas. `HttpClient` therefore sends a curl-like header set, and `arxiv_api.py` builds the query with literal commas. Keep both.
  - It also throttles after about 2 batches. The pipeline stops at the first failed batch, so the API is only a fallback.
- **Abstracts:** RSS first (one request for the latest day), then the API, then the paper's HTML page.
- **Affiliations:** submitter-declared ones from the API if present, otherwise heuristics on LaTeXML front matter (about 60% coverage). Add a fixture under `tests/fixtures/html/` for every new heuristic.
- **Fixtures:**
  - Real e-mails in them are replaced by `author@example.org`.
  - `tests/fixtures/` and `data/` are excluded from pre-commit, so hooks never rewrite them.
- **Contact:** `PREPRINT_RADAR_CONTACT` goes into the User-Agent. It comes from `.env` locally (git-ignored, loaded by the Makefile) and from a repository variable in CI.

## Gotchas

- The Makefile must run on macOS's GNU Make 3.81: no `--eval`, `.ONESHELL`, or `$(file ...)`.
- `web/vite.config.ts` serves `../data` at `/data` in dev and copies it into `dist/` on build. `base: "./"` keeps the site working under `user.github.io/<repo>/`.
- `web/tsconfig.node.json` type-checks `vite.config.ts` with Node types. The app itself only gets DOM types.
- GitHub Actions: pushes made with `GITHUB_TOKEN` do not trigger other workflows. That is why `update.yml` calls `deploy.yml` through `workflow_call`.

## Working agreements

- Do not commit, push, create the GitHub repo, or run the long `make update` unless asked.
- The maintainer writes in French. Answer in French, but keep everything in the repo in English.
