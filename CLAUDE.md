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
- `make backfill SINCE=YYYY-MM-DD [UNTIL=...]`: add past days from the catchup pages, then read their HTML pages (a month of cs.CV takes about 11 hours). Same rule: ask first. Interrupting either command loses nothing; re-running resumes.
- `make stats`: how much of `data/` is enriched (abstracts, affiliations, venues per day). Check it after touching the extraction heuristics.

Single checks: `uv run pytest tests/unit/test_store.py -k merge`, `cd web && npx vitest run tests/search.test.ts`.

## Layout

- `src/preprint_radar/`: `pipeline.py` orchestrates listing → abstracts → HTML front matter → store.
  - `update_category` follows the recent listing, `backfill_category` walks past days through catchup pages.
  - Sources: `listing.py` (recent listing and catchup pages, which share the entry markup), `rss.py`, `arxiv_api.py`, `paper_page.py`; `venue.py` detects accepted venues from comments at parse time.
  - HTTP goes through `http.HttpClient` only (rate limiting, retries, error mapping).
- `data/<category>/<YYYY-MM-DD>.json` + `data/index.json`: written by `store.py`, read by `web/src/data.ts`. Generated, but committed and deployed.
- `web/src/`: `search.ts` (MiniSearch index and query syntax), `app.tsx` (layout and wiring), `hooks/` (URL-synced view state, paper loading, reading list, theme), `url-state.ts` (shareable URLs, including `?paper=` paper permalinks), `period.ts` (preset or custom date range, `?range=` or `?from=&to=`, shown by `components/PeriodPicker.tsx`), `preferences.ts` (per-browser settings in `localStorage`).
  - Graph view: `graph.ts` builds the institution/author co-occurrence graph (pure, tested); `graph-layout.ts` gives starting positions (each connected component in one piece, on a spiral); `graph-renderer.ts` draws on a canvas with d3-force (imperative class); `components/GraphView.tsx` and `GraphSettingsPanel.tsx` are the UI. It is full screen, without the search bar and sidebar, and shows every node unless the user sets a limit.
  - With authors on, a month of papers is about 14,000 nodes and 60,000 links. The renderer batches drawing into a few `Path2D` per frame; graphs over 2,000 nodes use `theta` 1.2, no collisions and a faster cooling.
  - Never set `distanceMax` on the many-body force nor raise `theta` much: nodes then pile up in rings (seen with 1,200 and 1.8). Small components get extra gravity once the largest component is big, else its repulsion keeps them in a ring far around it.
- `tests/fixtures/`: trimmed copies of real arXiv pages (listing, catchup, RSS, API feed, HTML front matter).

## Conventions

- Everything in the repo is in English: code, comments, docs, CLI help, commit messages.
- Python 3.13+, fully typed, Google-style docstrings on public functions.
  - Ruff runs with `select = ["ALL"]`: fix the code rather than adding `noqa`. Keep any `noqa` or `ty: ignore` rare, and justify it inline.
- Errors are subclasses of `exceptions.PreprintRadarError`. The CLI turns them into a log line and exit code 1, never a traceback.
- Tests are offline. Mock HTTP with `httpx.MockTransport` injected into `HttpClient`, or monkeypatch `HttpClient.get_text` for CLI tests. Tests that hit the real arXiv live in `tests/integration/` with the `network` marker, which is deselected by default.
- Web: TypeScript strict (TS 7), Biome for lint and format (no ESLint/Prettier), Preact hooks, no CSS framework. Theme colors come from the CSS variables in `styles.css`: automatic light/dark plus a manual `data-theme` override. The dark palette is declared twice — keep both blocks identical, with plain values only (the graph canvas reads the variables through `getComputedStyle`).

## Data contract (keep both sides in sync)

- The paper record is defined by `Paper.to_record()` / `Paper.from_record()` in `models.py`, and mirrored in `web/src/types.ts`.
- A breaking change to the format means bumping `SCHEMA_VERSION` in both `store.py` and `types.ts`.
- `abstract` and `affiliations` use `null` for "not retrieved yet": the pipeline retries those.
- An empty list means "tried, nothing found"; the pipeline does not retry those.
- `affiliations` are per paper, deduplicated, and never contain e-mails or URLs.
- `author_affiliations` (optional, like `venue`) maps each author to indices into `affiliations`; `null` per author or altogether means "the page does not say". The graph links a placed author only to their own institutions.
- `venue` is optional on the web side (`venue?:`) because reading lists saved in browsers predate it. Adding an optional field needs no schema bump; backfill `data/` with a one-off script.

## arXiv constraints (hard-won, do not "simplify" away)

- **arxiv.org:** `robots.txt` asks for a 15 s crawl delay. It is used for the listing, RSS and HTML pages (`ARXIV_CRAWL_DELAY_SECONDS`).
- **export.arxiv.org (the API):**
  - Its firewall returns an empty `406` to httpx's default header order and to `%2C`-encoded commas. `HttpClient` therefore sends a curl-like header set, and `arxiv_api.py` builds the query with literal commas. Keep both.
  - It also throttles after about 2 batches. The pipeline stops at the first failed batch, so the API is only a fallback.
- **Abstracts:** RSS first (one request for the latest day), then catchup pages (one request per older day), then the API, then the paper's HTML page.
- **Catchup pages** (`/catchup/<category>/<YYYY-MM-DD>?abs=True`, allowed by `robots.txt`): one request per day, with abstracts.
  - Their new submissions and cross-lists are exactly the recent listing's entries for that day; replacements are skipped.
  - Days without announcement return 200 with "Total of 0 entries" and no section.
- **Affiliations:** submitter-declared ones from the API if present, otherwise heuristics on LaTeXML front matter. Add a fixture under `tests/fixtures/html/` for every new heuristic.
  - Sources, in order: `ltx_role_affiliation`/`ltx_role_address` contacts in `div.ltx_authors`; `ltx_note` of roles `address` and `institutetext` anywhere, and `footnotetext` notes that are direct children of the article and start with a marker; numbered lines after the names; "A is with B" sentences in `thanks` notes.
  - Superscript markers split affiliations; a line ending with "," or "and" continues on the next one, and a line that only names a place joins the previous line when that one has no country.
  - The author mapping reuses the same nodes, in tiers: per-creator contacts, superscript markers matched with marker-led (or marker-trailed) lines, "A is with B" sentences, plus the trivial single-affiliation/single-author cases. A wrong pair is worse than none: ambiguous name alignments drop the whole tier, unresolved authors stay `null`.
  - Raw LaTeX sources are **not** an alternative: `robots.txt` disallows `/e-print` and `/src` (export.arxiv.org disallows everything), and LaTeXML's HTML is already parsed LaTeX.
- **Fixtures:**
  - Real e-mails in them are replaced by `author@example.org`.
  - `tests/fixtures/` and `data/` are excluded from pre-commit, so hooks never rewrite them.
- **Contact:** `PREPRINT_RADAR_CONTACT` goes into the User-Agent. It comes from `.env` locally (git-ignored, loaded by the Makefile) and from a repository variable in CI.

## Gotchas

- The Makefile must run on macOS's GNU Make 3.81: no `--eval`, `.ONESHELL`, or `$(file ...)`.
- `web/vite.config.ts` serves `../data` at `/data` in dev and copies it into `dist/` on build. `base: "./"` keeps the site working under `user.github.io/<repo>/`.
- `web/tsconfig.node.json` type-checks `vite.config.ts` with Node types. The app itself only gets DOM types.
- GitHub Actions: pushes made with `GITHUB_TOKEN` do not trigger other workflows. That is why `update.yml` calls `deploy.yml` through `workflow_call`.
  - Actions are pinned by commit SHA with the version in a comment; bump them together (`git ls-remote --tags` gives the SHAs).
  - `update.yml` rebases its data commit before pushing (a run lasts hours), and its manual *since* input runs `backfill` instead of `update`.

## Working agreements

- Do not commit, push, create the GitHub repo, or run the long `make update` unless asked.
- The maintainer writes in French. Answer in French, but keep everything in the repo in English.
