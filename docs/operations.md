# Operations

What to do when the pipeline misbehaves, by symptom: *Update data* runs every weekday,
*Archive* on Sundays, the *arXiv canary* on Wednesdays. Each section starts with the
**signal** as the code prints it (`tests/unit/test_operations_doc.py` checks it still does).

Before touching `data/` by hand, check that no data workflow runs (`gh run list`), and never
push `data/` while one does: a conflict on a day file stops the bot's commit. After any
change, run `make validate`.

## Where to look

The run's page (*Actions → the run*): annotations, then the job summary (each command's
report line, *Data validation*, the newest day, the counts' age, coverage). The step log:
one greppable line per event, `HH:MM:SS LEVEL name: message`. Locally: `make stats`,
`make quality-affiliations`, `make validate`, `preprint-radar summary`.

## The outside scheduler

GitHub starts scheduled runs hours late, so [cron-job.org](https://cron-job.org)
dispatches the data workflows on time (set each job's time zone to UTC); the workflows' own
schedules are fallbacks.

| Workflow | Dispatched (UTC) | Fallback schedule (UTC) |
|---|---|---|
| *Update data* | Monday to Friday, 06:17 | 10:17 |
| *Archive* | Sunday, 05:41 | 09:41, and Saturday 05:41 when no run succeeded since Sunday |

Each job sends `POST
https://api.github.com/repos/titouanlegourrierec/preprint-radar/actions/workflows/<file>/dispatches`
with the body `{"ref":"main"}` and the headers `Authorization: Bearer <token>`,
`Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`; GitHub
answers `204`. The token is a fine-grained personal access token for this repository only,
with the single permission *Actions: Read and write* (it can start, cancel and delete runs
and caches, never read or push code). It expires: renew it before, in both jobs.

A dispatched run always goes on. A scheduled one first runs the `guard` job
(`.github/scripts/skip-if-done.sh`), which stops it once a run of the same workflow
succeeded that day (UTC). *Archive*'s Saturday catch-up (CI-8) looks back to Sunday, and
runs while the counts of failed Sunday runs are still cached (7 days). In a fork, every
scheduled run stops (notice `Fork`) and the *arXiv canary* skips its scheduled jobs.

### A scheduled run stopped at once

**Signal.** A notice `Already done today` on a scheduled run, whose `update` or `archive`
job is skipped, or `Already done this week` on a Saturday's *Archive*.

Normal: the day's dispatched run (or Sunday's) succeeded.

### A scheduled run did the work

**Signal.** No run with the event `workflow_dispatch` for the day, and a scheduled run
after 10:17 UTC (09:41 on Sundays) that did the work.

The dispatch failed; see the job's history on cron-job.org. `401`: the token expired or was
revoked (make a new one). `403` or `404`: it lacks this repository or its permission.
`422`: a wrong `ref` or body. A warning `Run history unavailable` means the guard could not
ask GitHub and let the run go on.

## Update data did not run, or started hours late

**Signal.** No *Update data* run for the day on the Actions page, or one started long
after 10:17 UTC; later, the summary's `Stale data` warning (`no new day for` more than
3 weekdays).

Nothing is lost while arXiv's listing still covers the missed days (its last five):

1. Run it by hand: *Actions → Update data → Run workflow*, or
   `gh workflow run update.yml`.
2. Older days catch up by themselves (CI-7): when the newest stored day is more than 4
   weekdays old (`CATCH_UP_WEEKDAYS`), or a day the listing dropped has papers pending,
   `update` reads every day since from the catchup pages, within 30 days (`CATCH_UP_DAYS`),
   with a warning `Catching up`. Papers without an HTML rendering (*no page* in
   `make stats`, about 5%) are never read.
3. A `Catching up` every day is one paper whose page never reads (a lasting 503): each run
   spends 7 minutes on catchup pages until that day is 30 days old. `make stats` names the
   day; `preprint-radar reextract --ids <id>` tries the page by hand.
4. Older than 30 days: fill *since* (`YYYY-MM-DD`); the run calls `backfill`, within 600
   pages (`DEFAULT_MAX_HTML`) unless *max-html* says otherwise.

## Update data is red

### arXiv is down

**Signal.** `HTML renderings in a row: stopping` (error annotation
`Reading HTML pages failed`).

Five pages failed in a row. What was read is pushed; the other papers stay pending (`null`)
for the next run. Nothing to do unless it repeats (<https://status.arxiv.org>).

### arXiv changed its page layout

**Signal.** `gave no affiliation: has arXiv's layout changed?` (error annotation
`Reading HTML pages failed`), often after a red *arXiv canary*.

90% of at least 40 pages gave no affiliation. The run's papers go back to pending (`[]`
would be final) and their pages leave the cache, so a passing error page heals by itself.
For a real change, `make test-network` shows what no longer parses: save one or two live
pages as fixtures in `tests/fixtures/html/` (e-mails replaced by `author@example.org`),
add them to `expected.json`, adapt `sources/arxiv_html.py` and bump `EXTRACTOR_VERSION`
(`docs/extraction.md`). Once pushed, the next runs read the pending papers again.

### The listing's entries lost their authors or links

**Signal.** "N of the M entries of the listing have no authors" (or no HTML link, or of
the catchup page): `the arXiv layout may have changed`, in the error annotation
*preprint-radar update failed*.

More than 10% of at least 20 entries had no author, or more than half no HTML link (REL-7),
so the run stored nothing. Fix `sources/arxiv_listing.py` against a saved copy of the page.

### A backfill left days unread

**Signal.** `the day is left for the next run` (error annotation `Catchup pages failed`),
and the report line ends with `days not read:` and the days.

A run with *since* (or `make backfill`) could not read those days' catchup pages (arxiv.org
down, a page that no longer parses, fewer entries than it announces). They are not saved,
since a saved day is never fetched again; after three in a row it stops asking
(`catchup pages in a row could not be read`: arxiv.org is down). Run it again over the same
days: only the missing ones are fetched. If a day keeps failing, the catchup layout
changed, which the canary does not test: check the page's dated title and "showing N of M
entries" headings against `parse_catchup` (`sources/arxiv_listing.py`).

### Validation failed: nothing was pushed

**Signal.** `Data validation` in the job summary lists `ERROR` lines; the *Commit data*
step is skipped and *Keep the data that failed validation* ran.

The data is kept, unpushed, in the run's `data-commit` artifact (7 days):

```bash
gh run download <run id> -n data-commit
git fetch data-commit.bundle HEAD:recovered-data
```

Check out `recovered-data`, fix what `make validate` reports (usually a code bug first,
with a test), and push; or do nothing, and the next run collects the same papers again.
Errors on `top-recent.json` ("archived too", "the papers of the last 12 months differ from
top-recent.json") mean the archive wrote one file and not the other: dispatch *Archive*
again (not on a Thursday or Friday: the week's gains need counts six days old).

### The data commit could not be pushed

**Signal.** `changed both in this run and on main; nothing was pushed.` or
`The data commit could not be pushed; nothing was pushed.`

`main` moved during the run on a file that `commit-data.sh` does not settle (any but
`index.json`, `citations.json`, `citation-gains.json`), or three pushes were refused.
Recover the `data-commit` artifact as above, rebase it on `main`, settle the conflict (keep
both sides' papers; `preprint-radar index` rewrites the index), validate and push.

### Semantic Scholar rejected the API key

**Signal.** Error annotation *preprint-radar citations failed* (or *archive*):
`Semantic Scholar rejected` the API key (HTTP 403 or 401).

The key is invalid or revoked (a valid one only ever gets 429s). Get a new one, run
`gh secret set SEMANTIC_SCHOLAR_API_KEY`, and update `.env` locally. Without a key,
requests still work, much more slowly.

### GitHub rejected the token

**Signal.** Error annotation *preprint-radar code failed* in the weekly *Archive* run, or
in *Update data* (`code --new`, the new papers' stars):
`GitHub rejected the token` (HTTP 401), or locally `No GitHub token: set` (`GITHUB_TOKEN`).

In CI it is the workflow's own token, refused for a while: a later run tries again, and the
stars stay as they were. Locally, put any token in `.env` (`GITHUB_TOKEN=`, no permission
needed), or run `GITHUB_TOKEN=$(gh auth token) make code`.

**Signal.** `GitHub refused the query` (a warning): a rate limit, or a query it would not
run. Those papers keep last week's stars; nothing to do unless it comes back every week.

**Signal.** `GitHub limits the queries` (info), then perhaps `GitHub kept limiting the
queries` (a warning): its secondary limits refused a query three times despite the waits
(`Retry-After`, else one minute, then two); the repositories left keep last week's stars.
If it comes back every week, raise `GITHUB_DELAY_SECONDS` (3 s) in the GitHub source.

### OpenAlex placed no institution

**Signal.** "OpenAlex lookup of 50 `institutions failed`" (a warning) in *Update data* or
*Archive* (`countries`, UX-40): OpenAlex refused or broke a request. The next run asks
again; meanwhile the map counts those papers in no country.

**Signal.** `The former countries.json does not load` (a warning): the file was broken,
so every institution is asked for again (about 90 requests).

## Update data is green, but something is off

### Out of time

**Signal.** Warning annotation `Out of time` (`HTML renderings left for the next run`, or
for a backfill `days left for the next run`).

The 175 minutes of *Fetch papers* ran out: the next runs read the rest. If it shows every
day, reading cannot keep up (more than 600 papers a day at 15 s a page): drop categories.

### The listing lacked today's announcement

**Signal.** Warning annotation `Listing out of date` (`the listing lacks` a day, whose
`papers come from its catchup page`), or `whose catchup page could not be read`.

arXiv's cache served the listing hours old, without a day announced late at night: the run
read that day's catchup page instead. Nothing to do; if that page could not be read, the
next run's listing has the day, or dispatch *Update data* with the day as *since*.

### Semantic Scholar keeps refusing

**Signal.** `Semantic Scholar keeps refusing; stopping after` in the citations step, or in
the weekly *Fetch the published versions* step.

It answered 429 until the step's budget ran out (10 minutes, 20 for the published
versions): the papers left get their counts, DOI and venue on a later run. Harmless and
green; if counts stop arriving, the summary warns `Stale citation counts` after 14 days.

**Signal.** `cannot answer for` (a warning, with what Semantic Scholar answered), or
`Semantic Scholar keeps answering batches that do not match; stopping after`. Such papers
are left out of the week's counts. A few are harmless; the same paper every week is an
arXiv id Semantic Scholar refuses: look it up by hand.

### A traceback that ends in KeyboardInterrupt

**Signal.** A traceback ending in `KeyboardInterrupt`, after `Interrupted: saving the`.

A cancelled run, a step timeout or Ctrl-C: the clean stop, after saving what was read.

## Archive did not change

**Signal.** Error annotation `Archive not updated` (`Too few citation counts`), and in
the log `of citation counts: the archive and day files stay as they are`.

Fewer than 95% of the candidates got a count: those fetched go into `citations.json`, the
archive stays as it was, and the run is red. Run *Archive* again by hand: the counts are
cached for 7 days in `.cache/catalog/`, so it resumes. Otherwise the fallback retries.

## Catalog cache evicted

**Signal.** The *Archive* log says `Harvesting` the set `(everything)` instead of
since a date, and the run takes about 45 minutes more, sooner than 90 days after the last
whole harvest (that run's log says the records that left the set `since its last whole
harvest`), which is due then (META-6).

GitHub evicts cache entries unused for 7 days, and *Update data* restores the catalog on
weekdays to keep it (CI-10): that step failed all week, or the entry was deleted. The
catalog is rebuilt from scratch; nothing else is lost.

## A whole harvest kept the catalog

**Signal.** The *Archive* log says `The whole set of` the category lists so many of the
catalog's records: `kept them all`.

The whole harvest, every 90 days, replaces the catalog so that removed records leave it;
this one listed under 99% of it (an OAI outage, or a renamed set), so it was merged
instead. If arXiv renamed its sets (`ListSets`), fix `Catalog.set_spec`; to harvest the
whole set sooner, delete `full` from `.cache/catalog/<category>.state.json` (in CI, the
cached catalog's).

## The trends kept last week's

**Signal.** Error annotation *preprint-radar trends failed* in the *Archive* run: the
catalog `holds no paper since 2010`, `archive harvests it`; or the warning
`No citation counts of the week in` the catalog's directory: `the topics' impact and key
papers are left out`.

`trends` reads the catalog the archive step harvested in the same run
([trends.md](trends.md)). Without it, `trends.json` and `topics.json` keep last week's:
run *Archive* again. Without the week's counts, the topics lack their impact and key
papers until the next archive. Locally, `make trends` reads your last `make archive`'s.

## Re-extract after a heuristic fix

- **Cleaning only** (`clean_affiliation`, `names_only_authors`): `make reclean`, then
  `make institutions` (changed strings lost their names), then `make validate`.
- **What a page gives** (affiliations, mapping): bump `EXTRACTOR_VERSION`; the daily
  *Extract stored papers again* step re-reads older versions, from the page cache and up to
  50 downloads a day. To repair papers at once: `preprint-radar reextract --ids <ids>` or
  `--match <regex>`.
- Before and after, run `make quality-affiliations` and `make extraction-diff` (with the
  page cache: what today's extraction changes, nothing written).
- **Signal** `cached pages gave no affiliation to papers that have some`: stale cached
  pages (`PageCache.stale`). Those papers keep what they had; the next run downloads their
  pages again. Nothing to do.

## Affiliations of the highly cited papers

The weekly *Archive* run calls `archive-affiliations`: OpenAlex's record of the published
version of each highly cited paper without affiliations (`docs/archive.md`).

**Signal.** `published versions: %s place the authors, %s name others` in the log: those
naming others are papers Semantic Scholar linked to a wrong DOI (24 of 7,027 in October
2026), which keep what they had. Nothing to do unless that count grows.

### Read their HTML pages (a night, on a machine of yours)

The papers no published version places (about 2,000 of 2024 and 2025, plus those of the
last 12 months) have HTML pages: 11 hours at 15 s a page, too long for a workflow. On a
machine with `git`, `make`, `uv`, a clone and a `.env` holding `PREPRINT_RADAR_CONTACT`,
in `tmux` or under `nohup`, after Sunday's *Archive* has pushed (it rewrites the same
files: the archive and `top-recent.json`) and before the next:

```bash
git pull
make archive-affiliations MAX_HTML=3000
make validate
git add data
git commit -m "chore(data): affiliations of highly cited papers from their HTML pages (AFF-28)"
git pull --rebase && git push
```

Running it again resumes: progress is saved every 20 pages and on Ctrl-C, and pages read
or answering 404 are never asked again. To stop before a time limit:
`uv run preprint-radar -v --contact <e-mail> archive-affiliations --max-html 3000
--deadline-minutes 480` (only the Makefile reads `.env`). If `git pull --rebase` conflicts:
`git rebase --abort`, `git reset --hard origin/main` (only the data commit is lost), and
run it again (minutes, from the cache). It stops red like the daily update
([arXiv is down](#arxiv-is-down), [layout changed](#arxiv-changed-its-page-layout)).

## Add a category

1. Set the repository variable `PREPRINT_RADAR_CATEGORIES` (space-separated, e.g.
   `cs.CV cs.LG`); both data workflows read it.
2. *Update data* reads the new listing's five days (about 750 pages) over two runs, 600
   pages a run at most (`DEFAULT_MAX_HTML`). Use *since* for older days.
3. The archive harvests the category's OAI set (`cs.LG` is `cs:cs:LG`, `astro-ph.CO`
   `physics:astro-ph:CO`) into its own archive, of the same budget (22,000 by default,
   `PREPRINT_RADAR_ARCHIVE_BUDGET`): its first run takes about 45 minutes more.
4. The About page names cs.CV: update it.

## The site or the repository grows too large

**Signal.** `Site too large` (the deploy fails) or `Site growing` in *Deploy site*;
`Repository growing` in the weekly *arXiv canary*.

Both sizes are on every run's page (`Site size`, `Repository size`). Pages refuses a site
over 1 GB: the deploy fails at 800 MB and warns at 600 MB. A year of cs.CV day files is
about 110 MB and pruning keeps one year (the archive stays near 50 MB), so the warnings
come with several categories. At a warning (the migration trigger, ARCH-1):

1. Check that pruning is on: the repository variable `PREPRINT_RADAR_ARCHIVE_PRUNE` is
   `true` (decision 2: older day files leave the site and the working tree, not the git
   history; the archive keeps their cited papers).
2. If the repository still grows past 500 MB, publish `data/` only through the Pages
   artifact and keep the store on an orphan `data` branch squashed monthly (or in
   releases, or a bucket); the workflows then commit there instead of `main`.

## How long things take

| Task | Duration |
|---|---|
| One HTML page | 15 s (arxiv.org's crawl delay) |
| Daily update | 40 minutes to 2 hours (200 to 400 papers) |
| Backfill of a month of cs.CV | about 11 hours (2,900 pages): five runs, or one with `MAX_HTML=3000` |
| Weekly archive of cs.CV | about 40 minutes with a key and a warm catalog; hours without |
| Catalog harvest, the first time and every 90 days | about 45 minutes |
| `institutions` (ROR), `code` (GitHub, the Hub) | minutes |
| `reextract` from the cache, `reclean`, `validate`, `stats`, `trends`, OpenAlex steps | seconds to a minute |
