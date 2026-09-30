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
- `make archive`: the weekly citation archive (refresh the OAI catalog, fetch citation counts, keep the most cited older papers). The first run takes about 2 hours without a Semantic Scholar key: ask first, like `make update`.
- `make institutions`: name the institutions of stored affiliations through the Research Organization Registry (ROR), for papers that `update`/`backfill` did not reach (a few minutes; one request per distinct string, every 0.5 s).
- `make stats`: how much of `data/` is enriched (abstracts, affiliations, venues per day). Check it after touching the extraction heuristics.

Single checks: `uv run pytest tests/unit/test_store.py -k merge`, `cd web && npx vitest run tests/search.test.ts`.

## Layout

- `src/preprint_radar/`: `pipeline.py` orchestrates listing → abstracts → HTML front matter → store.
  - `update_category` follows the recent listing, `backfill_category` walks past days through catchup pages.
  - Sources: `listing.py` (recent listing and catchup pages, which share the entry markup), `rss.py`, `arxiv_api.py`, `paper_page.py`; `venue.py` detects accepted venues from comments at parse time; `institutions.py` names the institution of each affiliation through ROR, after the HTML step.
  - HTTP goes through `http.HttpClient` only (rate limiting, retries on throttling, server errors and timeouts, error mapping).
  - Citation archive (weekly, `archive.py`): `catalog.py` harvests the category's OAI-PMH set into `.cache/catalog/` (git-ignored; restored from the Actions cache in CI), `citations.py` gets counts from Semantic Scholar, `selection.py` ranks papers older than 12 months by citations per year of age and keeps a budget of them (22,000 by default, about 20 citations a year; an archived paper leaves only beyond 1.15 times the budget), `openalex.py` gives the affiliations of papers that enter from the catalog. With less than 95% of citation counts, the archive stays as it is. Deleting day files older than 12 months (`--prune`) is off unless asked.
- `data/<category>/<YYYY-MM-DD>.json` + `data/index.json`: written by `store.py`, read by `web/src/data.ts`. Generated, but committed and deployed.
- `data/<category>/archive/<YYYY>.json` (papers kept for their citations, by year of first version, rewritten as a whole each week) and `data/<category>/citations.json` (counts of the stored papers). The index lists archive years under an optional `archives` key.
- `web/src/`: `search.ts` (MiniSearch index and query syntax), `app.tsx` (layout and wiring), `hooks/` (URL-synced view state, paper loading, reading list, theme), `url-state.ts` (shareable URLs, including `?paper=`: a paper permalink in the list, the focused paper in the graph), `period.ts` (preset or custom date range, `?range=` or `?from=&to=`, shown by `components/PeriodPicker.tsx`), `preferences.ts` (per-browser settings in `localStorage`).
  - Graph view: `graph.ts` builds the graph (pure, tested) from three layers: papers, institutions, authors. With papers on, a paper links to its authors, and each institution to the authors the paper places there, else to the paper itself (never to an unplaced author). With papers off, it is the co-occurrence projection (nodes linked when they share a paper). Default: papers + institutions, without isolated nodes; `graph-layout.ts` gives starting positions (each connected component in one piece, on a spiral); `graph-renderer.ts` draws on a canvas with d3-force (imperative class); `components/GraphView.tsx` and `GraphSettingsPanel.tsx` are the UI. It is full screen, without the search bar and sidebar, and shows every node unless the user sets a limit.
  - A month of papers (3,500) with all three layers is about 23,000 nodes and 34,000 links; the projection with authors has about 19,000 nodes and 100,000 links (every co-author pair). Papers + institutions (the default) is about 5,700 nodes and 6,700 links. The renderer batches drawing into a few `Path2D` per frame; graphs over 2,000 nodes use `theta` 1.2, no collisions and a faster cooling.
  - Never set `distanceMax` on the many-body force nor raise `theta` much: nodes then pile up in rings (seen with 1,200 and 1.8). Small components get extra gravity once the largest component is big, else its repulsion keeps them in a ring far around it.
- `tests/fixtures/`: trimmed copies of real arXiv pages (listing, catchup, RSS, API feed, HTML front matter).

## Conventions

- Everything in the repo is in English: code, comments, docs, CLI help, commit messages.
- Python 3.13+, fully typed, Google-style docstrings on public functions.
  - Ruff runs with `select = ["ALL"]`: fix the code rather than adding `noqa`. Keep any `noqa` or `ty: ignore` rare, and justify it inline.
- Errors are subclasses of `exceptions.PreprintRadarError`. The CLI turns them into a log line and exit code 1, never a traceback.
- Tests are offline. Mock HTTP with `httpx.MockTransport` injected into `HttpClient`, or monkeypatch `HttpClient.get_text` for CLI tests. Tests that hit the real arXiv live in `tests/integration/` with the `network` marker, which is deselected by default.
- Web: TypeScript strict (TS 7), Biome for lint and format (no ESLint/Prettier), Preact hooks, no CSS framework. Theme colors come from the CSS variables in `styles.css`: automatic light/dark plus a manual `data-theme` override. The dark palette is declared twice — keep both blocks identical (and give every new color, like the graph's `--graph-paper`, a value in all three blocks), with plain values only (the graph canvas reads the variables through `getComputedStyle`).

## Data contract (keep both sides in sync)

- The paper record is defined by `Paper.to_record()` / `Paper.from_record()` in `models.py`, and mirrored in `web/src/types.ts`.
- A breaking change to the format means bumping `SCHEMA_VERSION` in both `store.py` and `types.ts`.
- `abstract` and `affiliations` use `null` for "not retrieved yet": the pipeline retries those.
- An empty list means "tried, nothing found"; the pipeline does not retry those.
- `affiliations` are per paper, deduplicated, and never contain e-mails or URLs.
- `author_affiliations` (optional, like `venue`) maps each author to indices into `affiliations`; `null` per author or altogether means "the page does not say". The graph links a placed author only to their own institutions.
- `institutions` (optional) is parallel to `affiliations`: the ROR name of each affiliation's institution, `null` without a confident match, `null` altogether when not looked up yet (the pipeline retries). Anything that changes `affiliations` resets it to `null`. The web app names the rest itself (`web/src/institutions.ts`), and the affiliation filter matches both.
- Archived papers have the same record: `announced` is their first appearance (from the identifier's month when OAI's `created` disagrees), `html_url` is `null`, affiliations and `institutions` come from OpenAlex's institutions.
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
- **Institutions (ROR, `api.ror.org/v2/organizations?affiliation=`):** only `chosen` matches are kept, and only when one of the organization's names (not an acronym) of at least two words appears word for word in the affiliation: `chosen` alone matched "ARC Lab, Tencent" to an association called ARC and "180 Queen's Gate" to "The Gate". It covers about 65% of affiliation strings (universities in full); acronyms and companies are named by the web app's own rules, which map acronyms to ROR's names so both merge. A failing ROR never fails a run: lookups stop and resume next run.
- **Affiliations:** submitter-declared ones from the API if present, otherwise heuristics on LaTeXML front matter. Add a fixture under `tests/fixtures/html/` for every new heuristic.
  - Sources, in order: `ltx_role_affiliation`/`ltx_role_address` contacts in `div.ltx_authors`; `ltx_note` of roles `address` and `institutetext` anywhere, and `footnotetext` notes that are direct children of the article and start with a marker; numbered lines after the names; "A is with B" sentences in `thanks` notes.
  - Superscript markers split affiliations; a line ending with "," or "and" continues on the next one, and a line that only names a place joins the previous line when that one has no country.
  - elsarticle's `organization=…, city=…, country=…` text (printed verbatim by LaTeXML) ignores line breaks: a repeated key starts the next affiliation, and `clean_affiliation` turns the rest into plain values, organization first. Keep that conversion in `clean_affiliation` only, since the author mapping looks affiliations up through it.
  - Place-only affiliations written as separate contact nodes ("Carnegie Mellon University", then "Pittsburgh, PA 15213") are not joined: joining across nodes would also have to change every mapping tier.
  - The author mapping reuses the same nodes, in tiers: per-creator contacts, superscript markers matched with marker-led (or marker-trailed) lines, "A is with B" sentences, plus the trivial single-affiliation/single-author cases. A wrong pair is worse than none: ambiguous name alignments drop the whole tier, unresolved authors stay `null`.
  - Raw LaTeX sources are **not** an alternative: `robots.txt` disallows `/e-print` and `/src` (export.arxiv.org disallows everything), and LaTeXML's HTML is already parsed LaTeX.
- **Citation archive sources:**
  - OAI-PMH (`oaipmh.arxiv.org`, set `cs:cs:CV`): arXiv's sanctioned bulk metadata; no crawl delay in its robots.txt, 5 s between pages, about 45 minutes for the whole set. `created` is not always the first version's date.
  - Semantic Scholar (`paper/batch`, 500 arXiv ids a request): counts all versions of a paper. Anonymous requests are often refused (429) and retried patiently; `SEMANTIC_SCHOLAR_API_KEY` (repository secret) makes it minutes. OpenAlex undercounts published papers (×1.7 in median), so it is not used for counts.
  - OpenAlex (`works?filter=doi:10.48550/arxiv.<id>|...`, 50 a request): institutions per author; its raw affiliation strings are too rough to use.
- **Fixtures:**
  - Real e-mails in them are replaced by `author@example.org`.
  - `tests/fixtures/` and `data/` are excluded from pre-commit, so hooks never rewrite them.
- **Contact:** `PREPRINT_RADAR_CONTACT` goes into the User-Agent of arXiv requests only; other services (ROR...) get the bare `DEFAULT_USER_AGENT`, never the maintainer's e-mail. It comes from `.env` locally (git-ignored, loaded by the Makefile) and from a repository variable in CI.

## Gotchas

- The Makefile must run on macOS's GNU Make 3.81: no `--eval`, `.ONESHELL`, or `$(file ...)`.
- `web/vite.config.ts` serves `../data` at `/data` in dev and copies it into `dist/` on build. `base: "./"` keeps the site working under `user.github.io/<repo>/`.
- `web/tsconfig.node.json` type-checks `vite.config.ts` with Node types. The app itself only gets DOM types.
- GitHub Actions: pushes made with `GITHUB_TOKEN` do not trigger other workflows. That is why `update.yml` calls `deploy.yml` through `workflow_call`.
  - Actions are pinned by commit SHA with the version in a comment; bump them together (`git ls-remote --tags` gives the SHAs).
  - `update.yml` rebases its data commit before pushing (a run lasts hours), and its manual *since* input runs `backfill` instead of `update`.
  - `update.yml` checks out `main`, not the triggering commit: a run queued behind another one (concurrency group) otherwise starts from stale data and its rebase conflicts. Its cron (06:17 UTC) comes after arXiv's announcement and RSS rebuild; GitHub has been starting it hours late (around 10:00 UTC).

## Working agreements

- Do not commit, push, create the GitHub repo, or run the long `make update`, `make backfill` or `make archive` unless asked.
- The maintainer writes in French. Answer in French, but keep everything in the repo in English.
