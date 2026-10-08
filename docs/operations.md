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

## The outside scheduler

GitHub's scheduler starts scheduled runs hours late (06:17 runs started between 09:52 and
13:29 in the week of 2026-09-28; 2026-10-05's had not started at 12:20). So
[cron-job.org](https://cron-job.org) dispatches the data workflows on time, and their own
schedules are fallbacks, four hours later (set each cron-job.org job's time zone to UTC):

| Workflow | Dispatched (UTC) | Fallback schedule (UTC) |
|---|---|---|
| *Update data* | Monday to Friday, 06:17 | 10:17 |
| *Archive* | Sunday, 05:41 | 09:41 |

Each cron-job.org job sends `POST
https://api.github.com/repos/titouanlegourrierec/preprint-radar/actions/workflows/<file>/dispatches`
with the body `{"ref":"main"}` and the headers `Authorization: Bearer <token>`,
`Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`; GitHub
answers `204`. The token is a fine-grained personal access token for this repository only,
with the single permission *Actions: Read and write*: it can start, cancel and delete runs,
logs and caches, never read or push code. It expires: renew it before, and paste the new
one into both jobs.

A dispatched run always goes on. A scheduled one first runs the `guard` job
(`.github/scripts/skip-if-done.sh`), which stops it once a run of the same workflow has
succeeded that day (UTC), so a normal day has one run, and a failed or missing dispatch
is retried by the fallback. In a fork, the guard stops every scheduled run (a notice
`Fork`), so a fork that turns Actions on collects data only when its owner runs or
dispatches a workflow; the *arXiv canary* skips its jobs on schedule when the event says
the repository is a fork.

### A scheduled run stopped at once

**Signal.** A notice `Already done today` on a scheduled run, whose `update` or `archive`
job is skipped.

The normal case: the dispatched run of the day succeeded. Nothing to do.

### A scheduled run did the work

**Signal.** No run with the event `workflow_dispatch` for the day, and a scheduled run
after 10:17 UTC (09:41 on Sundays) that did the work.

The dispatch did not happen or failed. Look at the job's history on cron-job.org: a `401`
means the token expired or was revoked (create a new one, as above), a `403` or `404`
that it lacks this repository or its permission, a `422` a wrong `ref` or body. A warning
`Run history unavailable` means the guard could not ask GitHub and let the run go on.

## Update data did not run, or started hours late

**Signal.** No *Update data* run for the day on the Actions page, or one started long
after 10:17 UTC; later, the summary's `Stale data` warning (`no new day for` more than
3 weekdays).

Both the dispatch and the fallback schedule failed (see above). Nothing is lost while
arXiv's listing still covers the days missed (it shows the last five announcement days):

1. Run it by hand: *Actions → Update data → Run workflow* (or
   `gh workflow run update.yml`). Runs share a concurrency group, so a scheduled run
   queued meanwhile waits for the manual one, then stops at its guard if it succeeded.
2. For days older than the listing, fill *since* (`YYYY-MM-DD`): the run then calls
   `backfill` over the catchup pages from that day on, limited to 600 pages
   (`DEFAULT_MAX_HTML`) unless *max-html* says otherwise. Run it again until `make stats`
   shows no pending papers for those days; papers without an HTML rendering count as
   *no page*, which no run reads (about 5%).

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

### A backfill left days unread

**Signal.** `the day is left for the next run` (error annotation `Catchup pages failed`),
and the report line ends with `days not read:` and the days.

A run with *since* (or `make backfill`) could not read the catchup page of those days: it
failed (arxiv.org down, or a page that no longer parses), or listed fewer entries than it
announces. They are not saved, since a day saved with its abstracts is never fetched again;
the other days are, with their pages, then the run goes red (REL-4). After three days in a
row it could not read, it asks for no more (`catchup pages in a row could not be read`):
arxiv.org is down, and each day would cost a minute of retries. Run it again over the
same days: the days already stored are reused, so only the missing ones are fetched. If a
day keeps failing with `lists` fewer entries, or the page no longer parses, the catchup
layout changed. The canary does not read catchup pages, only the recent listing, whose
entries they share: open the day's catchup page and check its dated title and its
"showing N of M entries" headings, which `parse_catchup` (`sources/arxiv_listing.py`) reads.

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

On `top-recent.json` (the most cited papers of the last 12 months, PROD-11), "archived too",
an `announced` before its `since`, or "the papers of the last 12 months differ from
top-recent.json" in the index mean the archive wrote one file and not the other; the next
archive rewrites both, so dispatching *Archive* again settles it (not on a Thursday or
Friday if you want the week's gains: they need counts six days old).

### The data commit could not be pushed

**Signal.** `changed both in this run and on main; nothing was pushed.` or
`The data commit could not be pushed; nothing was pushed.`

`main` moved during the run on a file other than `index.json`, `citations.json` and
`citation-gains.json` (which `commit-data.sh` settles itself), usually a day file pushed by hand meanwhile, or three
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

**Signal.** Warning annotation `Out of time` (`HTML renderings left for the next run`, or
for a backfill `days left for the next run`).

The 175 minutes of *Fetch papers* ran out before every page was read (or, for a backfill
over several categories, before the later ones' catchup pages were asked for): a big day,
or a slow arxiv.org. Normal after a long gap; the next runs read the rest. If it shows every
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
  compares what is stored with what the extraction gives today, without writing. `make
  extraction-diff` lists the papers it changes, those that would lose words first.
- **Signal** `cached pages gave no affiliation to papers that have some`: pages kept before
  2026-10-06 lost the tables of their author block, where some classes write names and
  affiliations (2609.06629). Those papers keep what they had and their pages leave the
  cache: the next run downloads them, within its budget. Nothing to do.

## Affiliations of the highly cited papers

The weekly *Archive* run ends with `archive-affiliations`: OpenAlex's record of the
published version of each highly cited paper without affiliations (`docs/archive.md`).
Its line is in the job summary, under **Affiliations of the highly cited papers**.

**Signal.** `published versions: %s place the authors, %s name others` in the log: the
versions that name others are papers Semantic Scholar linked to a wrong DOI (24 of 7,027
in October 2026); they keep what they had. Nothing to do, unless that count grows.

### Read their HTML pages (a night, on a machine of yours)

The papers no published version places, about 2,000 of 2024 and 2025 and those of the
last 12 months, have HTML pages on arXiv: 15 s each, a night, which no workflow runs (its
minutes are billed). On a machine with `git`, `make` and `uv`, a clone of the repository
and a `.env` holding `PREPRINT_RADAR_CONTACT`, in `tmux` or under `nohup`:

```bash
git pull
make archive-affiliations MAX_HTML=3000
make validate
git add data
git commit -m "chore(data): affiliations of highly cited papers from their HTML pages (AFF-28)"
git pull --rebase && git push
```

- The most cited are read first; progress is saved every 20 pages and on Ctrl-C, and
  running it again resumes: pages already read come from `.cache/front-matter/`, offline,
  and those that answered 404 are not asked for again. To end it cleanly before a time
  limit: `uv run preprint-radar -v --contact <e-mail> archive-affiliations --max-html
  3000 --deadline-minutes 480` (only the Makefile reads `.env`).
- It writes only the archive and `top-recent.json`, which the weekly *Archive* run
  rewrites on Sundays (05:41 UTC): start once that run has pushed (the list of the last 12
  months is then this week's, and exists from 2026-10-11 on), and push before the next,
  never while *Update data* or *Archive* runs (`gh run list`). If `git pull --rebase`
  stops on a conflict all the same, `git rebase --abort`, `git reset --hard origin/main`
  (only the data commit is lost), then run it again: minutes, from the cache.
- It stops as the daily update does: red after 5 failed pages in a row (`HTML renderings
  in a row: stopping`) or nearly every page empty (`gave no affiliation: has arXiv's layout
  changed?`); what it read is saved, so look at the cause, then run it again.

## Add a category

1. Set the repository variable `PREPRINT_RADAR_CATEGORIES` (space-separated, e.g.
   `cs.CV cs.LG`). Both data workflows read it.
2. The first *Update data* run reads the five days of the new listing: about 750 pages,
   3 hours, of which a run reads at most 600 (`DEFAULT_MAX_HTML`), within the deadline
   the categories share; the next runs read the rest. Use *since* for older days.
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
by about 110 MB a year of cs.CV, and pruning keeps one year of them (the archive stays near
50 MB), so the warnings come with several categories.

At a warning (the migration trigger, decided with ARCH-1):

1. Check that pruning is on (decision 2: day files older than 12 months leave the site and
   the working tree, but stay in git history; the archive keeps their cited papers): the
   repository variable `PREPRINT_RADAR_ARCHIVE_PRUNE` is `true` since 2026-10-06.
2. If the repository still grows past 500 MB, publish `data/` only through the Pages
   artifact and keep the store on an orphan `data` branch squashed every month (or in
   releases, or a bucket); the workflows then commit there instead of `main`.

## How long things take

| Task | Duration |
|---|---|
| One HTML page | 15 s (arxiv.org's crawl delay) |
| Daily update | 40 minutes to 2 hours (200 to 400 papers) |
| First update of a category | about 3 hours (750 pages), over two runs |
| Backfill of a month of cs.CV | about 11 hours (2,900 pages), over five runs of 600 pages, or one with `MAX_HTML=3000` |
| Re-extraction from the page cache | seconds |
| `reclean`, `validate`, `stats` | seconds |
| `affiliations` (OpenAlex, papers without an HTML page) | seconds; 20 s the first time (225 papers) |
| `archive-affiliations` (OpenAlex, published versions) | seconds; 2 minutes the first time (7,076 DOIs) |
| `archive-affiliations MAX_HTML=3000` (HTML pages of highly cited papers) | 15 s a page: about 8 hours for the archive's 2,000, 3 more for the last 12 months |
| `institutions` | a few minutes (one request per distinct string, every 0.5 s) |
| First catalog harvest | about 45 minutes |
| Weekly archive of cs.CV | 207,000 counts in 415 requests: about 40 minutes with a key and a warm catalog; hours without a key |
