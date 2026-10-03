# Operations

What to do when the pipeline misbehaves, by symptom. The pipeline runs unattended:
*Update data* every weekday, *Archive* every Sunday, the *arXiv canary* every Wednesday.
Each section starts with the **signal**: what the run's page, its log or its job summary
says, quoted as the code prints it (`tests/unit/test_operations_doc.py` checks that every
quoted signal still exists in the code, so that this page cannot drift silently).

Before touching `data/` by hand, check that no data workflow is running
(`gh run list --workflow update.yml`, `--workflow archive.yml`): a conflict on a day file
stops the bot's commit. After any change, run `make validate`.

## Where to look

- **The run's page** (*Actions → the run*): annotations (yellow warnings, red errors) and
  the job summary: each command's report line, *Data validation*, then *Data*: the newest
  day, the age of the citation counts, and folded tables (coverage, signs of wrong
  affiliations).
- **The step log**: one line per event, `HH:MM:SS LEVEL name: message`, greppable.
- **Locally**: `make stats` (coverage), `make quality-affiliations` (signs of wrong
  affiliations), `make validate` (the contract), `preprint-radar summary` (freshness).

## Update data did not run, or started hours late

**Signal.** No *Update data* run for the day on the Actions page, or one started long
after 06:17 UTC; later, the summary's `Stale data` warning (`no new day for` more than
3 weekdays).

GitHub's scheduler delays and sometimes skips scheduled runs (it skipped 2026-10-01, and
started 2026-10-02 six hours late). Nothing is lost while arXiv's listing still covers the
days missed (it shows the last five announcement days):

1. Run it by hand: *Actions → Update data → Run workflow* (or
   `gh workflow run update.yml`). Runs share a concurrency group, so a late scheduled run
   waits for the manual one and then finds little to do.
2. For days older than the listing, fill *since* (`YYYY-MM-DD`): the run then calls
   `backfill` over the catchup pages from that day on, limited to *max-html* pages. Run it
   again until `make stats` shows no pending papers for those days.

## Update data is red

Open the run's annotations; the first error names the cause.

### arXiv is down

**Signal.** `HTML renderings in a row: stopping` (error annotation
`Reading HTML pages failed`).

Five pages failed in a row: arxiv.org was down or refusing. What was read is saved and
pushed; the other papers stay pending (`null`) and are read by the next run. Nothing to do
unless it repeats; then check <https://status.arxiv.org>.

### arXiv changed its page layout

**Signal.** `gave no affiliation: has arXiv's layout changed?` (error annotation
`Reading HTML pages failed`), often after a red *arXiv canary*.

90% of at least 40 pages gave no affiliation. The papers of this run are set back to
pending, since `[]` would be final, and their pages leave the page cache: if arXiv only
served an error page for a while, the next run downloads them again and heals by itself.
To fix a real change:

1. `make test-network` (or the canary's log) shows what no longer parses.
2. Save one or two live pages as fixtures in `tests/fixtures/html/` (replace e-mails with
   `author@example.org`), add their authors to `expected.json`, adapt
   `sources/arxiv_html.py`, and bump `EXTRACTOR_VERSION`.
3. Once pushed, the next runs read the pending papers again by themselves.

### Validation failed: nothing was pushed

**Signal.** `Data validation` in the job summary lists `ERROR` lines; the *Commit data*
step is skipped and *Keep the data that failed validation* ran.

A structural rule is broken (a record that does not load, a paper stored twice, an index
out of step…). The run's data is kept, unpushed, in the `data-commit` artifact (7 days):

```bash
gh run download <run id> -n data-commit
```

```bash
git fetch data-commit.bundle HEAD:recovered-data
```

Then check out `recovered-data`, fix what `make validate` reports (usually a bug to fix in
the code first, with a test), and push. If the data is not worth saving, do nothing: the
next run collects the same papers again.

### The data commit could not be pushed

**Signal.** `changed both in this run and on main; nothing was pushed.` or
`The data commit could not be pushed; nothing was pushed.`

`main` moved during the run on a file other than `index.json` and `citations.json` (which
`commit-data.sh` settles itself), usually a day file pushed by hand meanwhile, or three
pushes were refused. Recover the `data-commit` artifact as above, then rebase it on `main`,
settle the conflict (keep both sides' papers; `preprint-radar index` rewrites the index),
validate and push. Prevention: never push `data/` while a data workflow runs.

### Semantic Scholar rejected the API key

**Signal.** Error annotation *preprint-radar citations failed* (or *archive*):
`Semantic Scholar rejected` the API key (HTTP 403 or 401).

Every request of a valid key gets through or gets a 429; a 401 or 403 means the key is
invalid or revoked. Get a new key from Semantic Scholar, then:

```bash
gh secret set SEMANTIC_SCHOLAR_API_KEY
```

Locally, update `SEMANTIC_SCHOLAR_API_KEY` in `.env`. Without a key, requests still work,
much more slowly.

## Update data is green, but something is off

### Out of time

**Signal.** Warning annotation `Out of time` (`HTML renderings left for the next run`).

The 175 minutes of *Fetch papers* ran out before every page was read: a big day, or a
slow arxiv.org. Normal after a long gap; the next runs read the rest. If it shows every
day, reading cannot keep up (more than 600 papers a day at 15 s a page): lower the
categories or accept a backlog.

### Semantic Scholar keeps refusing

**Signal.** `Semantic Scholar keeps refusing; stopping after` in the citations step, or in the weekly
*Fetch the published versions* step.

Semantic Scholar answered 429 for 10 minutes (20 for the published versions): the new papers
get their counts on a later day, and the papers not asked for keep last week's DOI and venue.
Harmless, and the step stays green. If counts stop arriving altogether, the
summary's `Stale citation counts` warning shows it after 14 days.

### A traceback that ends in KeyboardInterrupt

**Signal.** A traceback ending in `KeyboardInterrupt`, after
`Interrupted: saving the`.

A cancelled run, a step timeout or Ctrl-C: the command saved what it had read, then
stopped. It is the clean stop, not a crash; the next run resumes.

## Archive did not change

**Signal.** Error annotation `Archive not updated` (`Too few citation counts`), and in
the log `of citation counts: the archive and day files stay as they are`.

Fewer than 95% of the candidates got a count, mostly because Semantic Scholar refused too
many batches. The counts fetched are merged into `citations.json` (its date stays), the
archive is left as it was, and the run is red. Run *Archive* again by hand: counts are
cached for 7 days in `.cache/catalog/`, so it resumes where it stopped.

## Catalog cache evicted

**Signal.** The *Archive* log says `Harvesting` the set `(everything)` instead of
since a date, and the run takes about 45 minutes more.

GitHub evicts Actions cache entries unused for 7 days, and the archive runs weekly. The
catalog is rebuilt from scratch (OAI-PMH is meant for it; 5 s between pages). Nothing
else is lost: the cached citation counts only serve a run that resumes within 7 days. If
it happens often, run *Archive* by hand mid-week to keep the entry warm.

## Re-extract after a heuristic fix

- **A change to the cleaning only** (`clean_affiliation`, `names_only_authors`): run
  `make reclean`, then `make institutions` (the changed strings lost their names), then
  `make validate`. Offline but for ROR; seconds.
- **A change to what a page gives** (affiliations, mapping): bump `EXTRACTOR_VERSION`.
  The daily *Extract stored papers again* step reads papers of older versions again, from
  the page cache (free) and up to 50 downloads a day. To repair older papers at once, name
  them: `preprint-radar reextract --ids <ids>` or `--match <regex>` (15 s a page not in
  the cache).
- Measure before and after with `make quality-affiliations`: with the page cache, it
  compares what is stored with what the extraction gives today, without writing.

## Add a category

1. Set the repository variable `PREPRINT_RADAR_CATEGORIES` (space-separated, e.g.
   `cs.CV cs.LG`). Both data workflows read it.
2. The first *Update data* run reads the five days of the new listing: about 750 pages,
   3 hours, so the deadline leaves some for the next runs. Use *since* for older days.
3. The archive harvests the category's OAI set (derived from the category: `cs.LG` is
   `cs:cs:LG`) and gives it its own archive, of the same budget (22,000 by default,
   `PREPRINT_RADAR_ARCHIVE_BUDGET`): the first run takes about 45 minutes more, and asks
   Semantic Scholar for the new category's counts too.
4. The site lists the categories of `index.json` and opens the first in alphabetical
   order. The About page names cs.CV: update it.

## The site or the repository grows too large

**Signal.** `Site too large` (the deploy fails) or `Site growing` in *Deploy site*;
`Repository growing` in the weekly *arXiv canary*.

Both sizes are on the runs' pages every time (`Site size`, `Repository size`). GitHub Pages
refuses a site over 1 GB: the deploy fails at 800 MB and warns at 600 MB. Day files grow
by about 110 MB a year of cs.CV while pruning is off (the archive stays near 50 MB), so
the warnings come with several categories, or after years of one.

At a warning (the migration trigger, decided with ARCH-1):

1. Turn pruning on, if it is not (decision 2: day files older than 12 months leave the site
   and the working tree, but stay in git history; the archive keeps their cited papers):
   set the repository variable `PREPRINT_RADAR_ARCHIVE_PRUNE` to `true`.
2. If the repository still grows past 500 MB, publish `data/` only through the Pages
   artifact and keep the store on an orphan `data` branch squashed every month (or in
   releases, or a bucket); the workflows then commit there instead of `main`.

## How long things take

| Task | Duration |
|---|---|
| One HTML page | 15 s (arxiv.org's crawl delay) |
| Daily update | 40 minutes to 2 hours (200 to 400 papers) |
| First update of a category | about 3 hours (750 pages), over two runs |
| Backfill of a month of cs.CV | about 11 hours |
| Re-extraction from the page cache | seconds |
| `reclean`, `validate`, `stats` | seconds |
| `institutions` | a few minutes (one request per distinct string, every 0.5 s) |
| First catalog harvest | about 45 minutes |
| Weekly archive of cs.CV | 207,000 counts in 415 requests: about 40 minutes with a key and a warm catalog; hours without a key |
