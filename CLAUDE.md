# CLAUDE.md

Preprint Radar: a Python pipeline collects the papers announced daily on arXiv (listing,
abstracts, affiliations) into `data/`, and a static Preact app in `web/` lets people search
them. It is deployed on GitHub Pages; there is no server.

## Read before changing

- `sources/arxiv_html.py`, `venue.py`, the cleaning or the author mapping: `docs/extraction.md`.
  Every rule there came from a real page; never "simplify" one away.
- `archive/`, `sources/semantic_scholar.py`, `sources/openalex.py`, `sources/arxiv_oai.py`:
  `docs/archive.md`.
- `web/`: `docs/web.md`, for the part you touch.
- A workflow, a failure or a log line: `docs/operations.md`, the runbook by symptom. Its
  signals are quoted from the code, and `tests/unit/test_operations_doc.py` fails when one
  no longer exists.
- `docs/roadmap.md` tracks the audit's items (`docs/audit/2026-09-30.md` is a frozen
  snapshot: never edit it).

## Commands

Use the Makefile; `make help` lists every target (`install`, `build`, `clean`, `pre-commit`…).

- `make check`: what CI runs, `make quality` (ruff format and lint, ty, Biome, tsc,
  actionlint) then `make test` (pytest and Vitest, offline). Run it before saying a change
  is done. Single checks: `uv run pytest tests/unit/test_paper_store.py -k merge`,
  `cd web && npx vitest run tests/search.test.ts`.
- `make coverage`: Python line and branch coverage; CI fails below 95% (`fail_under`). Keep
  it at 100%: test new code, or exclude a line that cannot run with a `# pragma: no cover`
  / `no branch` that says why. Vitest fails a pure web module (`src/**/*.ts` but hooks and
  what needs a DOM) below 90% of lines or 70% of branches (`vite.config.ts`): test a new
  module there.
- `make test-e2e`: the smoke test of the built site (`web/e2e/smoke.spec.ts`, Playwright,
  Chromium), over the small store of `web/e2e/data` (`PREPRINT_RADAR_DATA_DIR`): the list,
  a search in the URL, paper links (archived ones included, with their merged venue and
  DOI), the graph, no page error. CI runs it after the build; keep `e2e/data` valid when
  the format changes. `make test-network`: the parsers against the live arXiv (slow).
- `make format`: auto-fix formatting and lint. `make dev` / `make preview`: the site locally.
- Long runs, **never without asking**; interrupting loses nothing, re-running resumes:
  - `make update` (reads HTML pages at one every 15 s: hours). `make update-quick` skips
    the pages.
  - `make backfill SINCE=YYYY-MM-DD [UNTIL=...]`: past days from the catchup pages, then
    their pages (a month of cs.CV: about 11 hours).
  - `make archive`: the weekly citation archive; about 207,000 counts in 415 Semantic
    Scholar requests, hours without a key, and 45 minutes of catalog harvest the first time.
- Network steps of the workflows, minutes each:
  - `make institutions`: ROR names, and their ids, for stored affiliations that have none
    (one request per distinct string every 0.5 s, within a budget; new papers first).
  - `make citations`: Semantic Scholar counts of the stored papers without one; `ALL=1` asks
    for every paper again. The daily workflow runs it.
  - `make scholar`: the DOI, published venue and author ids of every stored paper into
    `scholar.json` (52 requests). `archive.yml` runs it weekly.
  - `make reextract [MAX_HTML=N]`: read again the pages of stored papers extracted by an
    older `EXTRACTOR_VERSION`, from the page cache when it holds them (offline), else at
    15 s a page within `MAX_HTML`; `--ids` or `--match REGEX` pick papers instead. A page
    that cannot be read leaves the paper as it was. The daily workflow runs it (50
    downloads at most). Papers read before versions were kept have none: only `--ids`
    or `--match` reach them.
- Offline, seconds, after a change to the rules (then commit the data):
  - `make reclean`: today's affiliation cleaning on the stored day files (strings cleaned
    and split, author names dropped, the mapping follows, changed papers lose their
    institutions: run `make institutions` after). Never the archive (OpenAlex names).
  - `make venues`: today's venue detection on every stored paper, archive included.
- Reports:
  - `make validate`: `data/` against its contract (`store/validate.py`, 2 s). Errors fail
    it: a record that does not load, a paper stored twice, a file named after another day
    or year, an index or `citations.json` that disagrees with the files, a `scholar.json`
    that does not load, a contact detail in an affiliation. Warnings: an affiliation that
    only names authors, the last author alone holding every affiliation, a paper `reclean`
    would change, stale `scholar.json` records. Run it after touching `data/` by hand.
  - `make stats`: enrichment per day and per archive year (abstracts, affiliations,
    mappings, institutions, venues detected or published, citation counts).
  - `make quality-affiliations` (`stats --affiliations`, `store/quality.py`): signs of wrong
    affiliations (author names, strings today's cleaning would change, "is with" sentences,
    glued or cut-off strings, units without their institution, a place alone, the last
    author holding all), 5 examples each. With `--page-cache-dir`, the cached pages as
    stored and as extracted today, nothing written: run it before and after a heuristic
    change. Approximate (a few false positives each).
  - `preprint-radar summary`: the newest day of each category and its age, the date of the
    counts, the `stats` tables and quality counts. The data workflows run it last; in
    Actions, `console.github_summary` and `console.github_annotation` put it and each
    command's report line on the run's page, with warnings for stale data (no new day for
    more than 3 weekdays) or stale counts (14 days), and errors for red failures.

## Layout

- `src/preprint_radar/`:
  - `sources/`: one module per service, each fetching and parsing: `arxiv_listing.py`
    (recent listing and catchup pages, which share the entry markup), `arxiv_rss.py`,
    `arxiv_api.py`, `arxiv_html.py` (front matter: affiliations, author mapping, abstract;
    `PageCache`), `arxiv_oai.py`, `semantic_scholar.py` (counts and published versions),
    `openalex.py` (institutions of archived papers), `ror.py` (institution of a string).
  - `collect.py`: listing → abstracts → HTML front matter → institutions → store
    (`update_category`, `backfill_category`, `reextract_category`; `HtmlReading` bundles
    how pages are read), and the Semantic Scholar steps (`update_citation_counts`,
    `update_scholar_records`). `venue.py`: venues from comments, and Semantic Scholar's
    named the same way.
  - `archive/`: the weekly citation archive (`update.py`, `catalog.py`, `selection.py`).
  - `store/`: `paper_store.py` (the `data/` layout), `validate.py`, `stats.py`,
    `quality.py`, `reclean.py`, `venues.py`, `export.py`, `filters.py`.
  - `config.py`: tunable defaults (category, directories, environment variable names,
    archive budget and policy, ROR lookups per run). Limits a service imposes (crawl
    delays, batch sizes, URLs, timeouts, retries) are not settings: they stay in that
    service's module, next to the reason for their value.
  - HTTP goes through `http.HttpClient` only (rate limiting, retries on throttling, server
    errors and timeouts, error mapping).
  - Output goes through `console.py`: `console.print` (never `print`) and
    `configure_logging`. rich styles it only in a terminal; CI, pipes and tests get plain,
    unwrapped lines (`09:52:13 INFO name: message`), so logs stay greppable and tests
    assert on text. `stats` draws rich tables in a terminal, the plain `format_*` text
    elsewhere.
- `data/` (generated, committed and deployed; written by `store/paper_store.py`):
  - `index.json`: categories, days, archive years (optional `archives`) and counts.
  - `<category>/<YYYY-MM-DD>.json`: the papers announced that day.
  - `<category>/archive/<YYYY>.json`: papers kept for their citations, by year of first
    appearance, rewritten as a whole each week.
  - `<category>/citations.json` and `<category>/scholar.json`: Semantic Scholar's counts
    and published versions of every stored paper, kept out of the records since they are
    rewritten weekly.
- `web/`: `src/` (the app; `docs/web.md`), `tooling/` (build plugins: what the site derives
  from `data/`, the third-party guard), `tests/` (Vitest), `e2e/` (Playwright and its store).
- `.cache/` (git-ignored; the Actions cache in CI): `front-matter/<yymm>/<id>v<n>.html.gz`,
  the front matter of every HTML page read (1 or 2 KB, extracts exactly as the whole page,
  which a network test checks), and `catalog/` (the OAI catalog and the counts cache).
- `tests/fixtures/`: trimmed copies of real arXiv pages; `html/expected.json` pins what each
  HTML fixture gives (`docs/extraction.md`). Real e-mails in them are replaced by
  `author@example.org`. Git hooks never rewrite `tests/fixtures/` or `data/`.

## Conventions

- Everything in the repo is in English: code, comments, docs, CLI help, commit messages.
- Python 3.13+, fully typed, Google-style docstrings on public functions. Ruff runs with
  `select = ["ALL"]`: fix the code rather than adding `noqa`; keep any `noqa` or
  `ty: ignore` rare, and justify it inline.
- Errors subclass `exceptions.PreprintRadarError`; the CLI turns them into a log line, an
  error annotation in Actions (`preprint-radar <command> failed`) and exit code 1, never a
  traceback.
- Tests are offline: mock HTTP with `httpx.MockTransport` injected into `HttpClient`, or
  monkeypatch `HttpClient.get_text` for CLI tests. Live tests live in `tests/integration/`
  with the `network` marker, deselected by default. Data made up for a test is synthetic:
  no real author ids or e-mails (the fixtures' real pages have theirs replaced).
- `tests/conftest.py` runs every test in its own temporary directory, since default paths
  are relative (`data/`, `.cache/`, `exports/`): a CLI test once wrote fake pages into the
  real page cache. It also hides `PREPRINT_RADAR_CONTACT`, `SEMANTIC_SCHOLAR_API_KEY` (the
  Makefile exports `.env`), `GITHUB_ACTIONS` and `GITHUB_STEP_SUMMARY`: set them with
  `monkeypatch.setenv` where a test needs them.
- Web: TypeScript strict (TS 7), Biome (no ESLint/Prettier), Preact hooks, no CSS
  framework. Theme colors are the CSS variables of `styles.css`: automatic light/dark plus
  a manual `data-theme` override. The dark palette is declared twice: keep both blocks
  identical, give every new color (like `--graph-paper`) a value in all three blocks, with
  plain values only (the graph canvas reads them through `getComputedStyle`);
  `tests/styles.test.ts` checks it. Text and links pass WCAG AA in both themes: form
  fields use `--border-strong`, links inside text are underlined, `mark` keeps `--text`.
- `web/tsconfig.node.json` type-checks `vite.config.ts`, `playwright.config.ts`,
  `tooling/` and `e2e/` with Node types; the app only gets DOM types.

## Data contract (keep both sides in sync)

- The paper record is `Paper.to_record()` / `Paper.from_record()` in `models.py`, mirrored
  in `web/src/types.ts`. A breaking change bumps `SCHEMA_VERSION` in both
  `store/paper_store.py` and `types.ts`. An optional field needs no bump: backfill `data/`
  with a one-off script, and give it `?:` on the web side, since reading lists saved in
  browsers predate it (`venue` is optional for that reason).
- `null` means "not retrieved yet" (`abstract`, `affiliations`, `institutions`): the
  pipeline retries. An empty list means "tried, nothing found": it does not, but for an
  archived paper under two years old, which OpenAlex is asked again every 30 days after
  the day of its last lookup (`provenance`, AFF-3): it learns recent papers over months.
- A paper is stored once, on the first day it was announced: a cross-list is sometimes
  announced again days later (2609.10714), and `PaperStore.save` keeps it on its earlier
  day, or moves it there.
- `affiliations` are per paper, deduplicated, and never contain e-mails or URLs.
- `author_affiliations` (optional) maps each author to indices into `affiliations`; `null`
  per author or altogether means "the page does not say". It is positional: `Paper`
  refuses one without one entry per author or with an index outside `affiliations`. When
  a new version changes the author list (beyond a respelling, `name_key`), `update` resets
  the affiliations so that the HTML is read again; without an HTML rendering, it keeps the
  affiliations and drops the mapping. The graph links a placed author only to their own
  institutions.
- `institutions` (optional) is parallel to `affiliations`: the ROR name of each one's
  institution, `null` without a confident match. Anything that changes `affiliations`
  resets it to `null`. The web app names the rest itself (`web/src/institutions.ts`), and
  the affiliation filter matches both.
- `institution_ids` (optional, written only when known) is parallel to `institutions`: the
  ROR id of each ("03vek6s52"), `null` without one. `Paper` refuses ids without
  institutions or not one per affiliation, so wherever `institutions` is set or reset, the
  ids go with it (a forgotten reset fails the tests). Institutions named before October
  2026 have none: `institutions` asks ROR again, keeping each name and taking only the id
  of a name ROR gives again; the archive asks OpenAlex again (`docs/archive.md`).
- `extractor` (optional, written only when known): the version of the HTML extraction that
  gave the affiliations; absent when they came from the API or OpenAlex, or were read
  before versions were kept. `reextract` selects on it, so a paper read from the API is
  never overwritten by its HTML.
- `withdrawn` (optional, written only when true): the comments say its authors or arXiv
  withdrew it (`withdrawal.is_withdrawn`, decision 18), set wherever `venue` is and
  refreshed with the comments; such a paper never enters the archive, and the site marks
  it.
- `provenance` (optional, written only when known): where `affiliations` came from
  (`html`, `api`, `openalex`) and who named `institutions` (`ror`, `openalex`), each with
  the day (`at`) it was read (`models.Provenance`, META-3). `Paper` refuses a provenance
  without its field, so it is reset with it, like the ids. Records stored before it got
  one inferred once, without a day (`store/provenance.py`); affiliations read before
  versions were kept, without a mapping, have none: the API or an unmapped page.
- Archived papers have the same record: `announced` is their first appearance,
  `html_url` is `null`, and affiliations, `institutions` and `institution_ids` come from
  OpenAlex.
- The site's records are not quite the store's: the build adds `doi` and, where the
  comments name no venue, the published `venue` from `scholar.json`. The pipeline never
  writes `doi` into a record.

## arXiv and service rules (hard-won, do not "simplify" away)

- **arxiv.org:** `robots.txt` asks for a 15 s crawl delay, used for the listing, RSS and
  HTML pages (`ARXIV_CRAWL_DELAY_SECONDS`). `robots.txt` disallows `/e-print` and `/src`:
  raw LaTeX is not an option.
- **export.arxiv.org (the API):** its firewall returns an empty `406` to httpx's default
  header order and to `%2C`-encoded commas, so `HttpClient` sends a curl-like header set
  and `sources/arxiv_api.py` builds the query with literal commas: keep both. It throttles
  after about 2 batches; the pipeline stops at the first failed batch, so the API is only
  a fallback.
- **Abstracts:** RSS first (one request for the latest day), then catchup pages
  (`/catchup/<category>/<YYYY-MM-DD>?abs=True`, allowed by `robots.txt`, one request a
  day), then the API, then the paper's HTML page. A catchup page's new submissions and
  cross-lists are exactly the recent listing's entries for that day (replacements are
  skipped); a day without announcement returns 200 with "Total of 0 entries".
- **Affiliations:** a fixture under `tests/fixtures/html/` for every new heuristic, and an
  `EXTRACTOR_VERSION` bump for any change to what a page gives (`docs/extraction.md`).
- **ROR:** only `chosen` matches whose name of at least two words appears in the string; a
  failing ROR never fails a run.
- **Semantic Scholar:** refusals (429) are routine even with a key and are retried; a 401
  or 403 means a bad key and fails the run (`docs/archive.md`).
- **Contact:** `PREPRINT_RADAR_CONTACT` goes into the User-Agent of arXiv requests only;
  other services get the bare `DEFAULT_USER_AGENT`, never the maintainer's e-mail. It
  comes from `.env` locally (git-ignored, loaded by the Makefile) and from a repository
  variable in CI.

## Gotchas

- The Makefile must run on macOS's GNU Make 3.81: no `--eval`, `.ONESHELL`, or `$(file ...)`.
- `web/vite.config.ts` derives files that only the site has (citation shards, the merged
  DOIs and venues): they never exist in `data/` (`docs/web.md`). The build fails if the
  site would load anything from another origin.
- GitHub Actions:
  - Pushes made with `GITHUB_TOKEN` trigger no other workflow, so `update.yml` and
    `archive.yml` call `deploy.yml` (`workflow_call`) when the bot pushed, also after a
    later failure, since the partial data was pushed. Bot pushes skip `ci.yml`, whose
    `data` job validates the other pushes.
  - A failure that touches data makes the run red (decision 16); a refusing Semantic
    Scholar does not.
  - Actions are pinned by commit SHA with the version in a comment; bump them together
    (`git ls-remote --tags` gives the SHAs).
  - `update.yml` and `archive.yml` share a concurrency group, check out `main` (not the
    triggering commit, else a queued run starts from stale data), run
    `.github/scripts/validate-data.sh` (a structural error pushes nothing), and commit
    through `.github/scripts/commit-data.sh`, which rebases onto a `main` that moved during
    the run: on a conflict it writes `index.json` again and keeps the run's
    `citations.json`; on any other conflict, or after three refused pushes, it uploads the
    commit as `data-commit.bundle` (`tests/unit/test_commit_data.py`).
  - Reading HTML pages stops early three ways (`collect.Stop`): the deadline (CI passes 175
    of the step's 195 minutes: green, the rest waits), 5 failed pages in a row (arxiv.org
    down: red), or 90% of at least 40 pages without affiliation (a layout change: red, the
    run's papers set back to pending and their pages dropped from the cache).
    `tests/unit/test_exit_criteria.py` runs these end to end. SIGTERM and Ctrl-C save the
    progress first.
  - GitHub starts schedules hours late, so cron-job.org dispatches both data workflows on
    time (`docs/operations.md`, with a token only the maintainer holds). Their schedules
    are fallbacks four hours later, whose `guard` job (`.github/scripts/skip-if-done.sh`)
    stops them once a run of the day succeeded; a dispatched or manual run always goes on.
  - `update.yml` (dispatched 06:17 UTC on weekdays): the update, then `reextract`
    (50 downloads, 12 minutes), `citations` (10 minutes), commit; 240 minutes in all. It
    restores the page cache from the Actions cache (`front-matter-<run id>`, saved even
    after a failure). Its manual *since* input runs `backfill` instead.
  - `archive.yml` (dispatched Sundays 05:41 UTC): the archive, then `scholar` (20 minutes).
  - `canary.yml` (Wednesdays): the network tests against the live arXiv (a red canary is a
    layout change to look at before it reaches the data), and the repository size.
  - Sizes (ARCH-1): `deploy.yml` fails a site above 800 MB (Pages refuses 1 GB) and warns
    above 600 MB; `canary.yml` warns above 500 MB of repository. Either triggers moving
    `data/` off `main` (`docs/operations.md`); pruning, a rolling year of day files
    (decision 2), is on since 2026-10-06 (`PREPRINT_RADAR_ARCHIVE_PRUNE`).

## Working agreements

- The maintainer writes in French: answer in French; everything in the repo stays English.
- Commit freely, in small commits that name the roadmap item they change (`fix(collect): …
  (DATA-2)`), with its status updated in `docs/roadmap.md` in the same commit. Never push,
  create the GitHub repo, or start `make update`, `make backfill` or `make archive`
  unless asked.
- Do not push changes under `data/` while *Update data* or *Archive* runs (`gh run list`):
  a conflict on a day file stops the bot's commit.
- Versions stay 0.x: a minor release at the end of each roadmap phase (a `v0.N.0` tag,
  `version` bumped in `pyproject.toml` and `web/package.json` together, a `CHANGELOG.md`
  entry), a patch for a fix in between. Pushing the tag creates the GitHub release with
  that entry as notes (`release.yml`, `.github/scripts/release-notes.sh`, which fails
  without one). 1.0.0 comes once the public data format is documented and stable.
