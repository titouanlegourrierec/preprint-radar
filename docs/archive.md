# The citation archive and the scholarly sources

The weekly archive (`archive/`), the citation counts, the published versions and the stars
of the papers' code, and what Semantic Scholar, OpenAlex, arXiv's OAI-PMH, GitHub and the
Hugging Face Hub are like to work with. Files and fields: [data-format.md](data-format.md);
failures and what to do: [operations.md](operations.md).

## The weekly archive (`archive/update.py`, `archive.yml`, Sundays)

- **Catalog** (`archive/catalog.py`): the category's OAI-PMH set as `ListSets` names it
  (`cs:cs:CV`, `physics:hep-th`), kept in `.cache/catalog/` (the Actions cache in CI). It
  asks weekly for the records modified since the last harvest and drops those OAI says were
  deleted. A cross-list removed from the set is not among them, so every 90 days
  (`FULL_HARVEST_DAYS`) the whole set (about 45 minutes) replaces the catalog, unless it
  lists fewer than 99% of its records: then it is merged, with a warning (META-6).
- **Candidates**: every catalog paper since 2010 (about 207,000, counted in 415 Semantic
  Scholar requests) and every day-file paper, first seen on the earlier of its day and the
  catalog's date (which can be weeks later). A day-file paper the catalog does not list
  competes on its day, which pruning would otherwise delete unranked (CIT-14). An archived
  paper that neither holds leaves.
- **Selection** (`archive/selection.py`): papers first seen over 12 months ago, ranked by
  citations per year of age (`max(age, 1)`). The best 22,000 enter (`DEFAULT_BUDGET`,
  about 20 citations a year); an archived one leaves only beyond 1.15 times the budget
  (`DEFAULT_MARGIN`), so that papers near the limit do not come and go. Each year at least
  three years old also keeps its most cited tenth (`year_floor`, decision 22); the run
  logs how many only that floor keeps. Never-cited papers are never kept, nor withdrawn
  ones (`withdrawn`, from the latest comments): an archived one leaves (decision 18).
- **Records**: a paper from a day file or last week's top-recent keeps its record, filed
  under its first appearance (an old paper cross-listed lately goes to its own year). One
  built from the catalog: `announced` its first appearance (the identifier's month when
  OAI's `created` disagrees), `html_url` `null`, OpenAlex's affiliations, subjects as the
  listings name them (`archive/subjects.py`, META-8: an alias as its canonical subject,
  listed once; an unknown code bare), authors without the author list's footnote marks,
  leading "and " or "others" (`arxiv_oai.author_names`, AFF-21). Each week
  the same cleaning reaches the papers no day file holds (`cleaned`), a dropped author
  keeping its place in the mapping. Day files keep the listing's names.
- **Comments** (`refreshed`, META-2): every stored paper takes the comments, journal
  reference and venue of its latest version from the catalog, which never empties a field.
  It needs a fresh harvest, so it runs only here, even below the coverage gate.
- **Cohorts** (`cohorts.json`, `year_cohorts`): each complete year since 2010, withdrawn
  papers left out: its size and the citations of the last of its top 1%, 5% and 10%.
- **Coverage gate**: below 95% of candidates counted (`MIN_COVERAGE`), the archive,
  top-recent, cohorts and day files stay; the counts fetched are merged into
  `citations.json`, keeping its date, and the command fails after writing them (CI still
  commits). Above it, an archived or top-recent paper missing a count keeps last week's.
- **Pruning** (`--prune`; `PREPRINT_RADAR_ARCHIVE_PRUNE` in CI) deletes the day files older
  than 12 months (decision 2). It decides nothing else: an archived paper can be in one.

## Why citations per year of age (the calibration of September 2026)

From a study of every cs.CV paper since 2010 (206,740 with cross-lists; Semantic Scholar
found 99.6%), whose scripts stay in the git-ignored `experiments/2026-09-citations/`
(DOC-4). A fixed threshold favors old papers: 500 citations keep 486 papers of 2018 but
64 of 2025. Per year of age, of the 160,466 papers older than a year, 10 citations a year
keep 41,537, 20 keep 22,619 (9,385 older than 5 years), 50 keep 8,252, 100 keep 3,440.
Hence 22,000, about 20 a year: a budget that rises with the field, not a threshold moved
by hand; about 55 MB at 2.5 KB a paper. A paper of 12 months has few citations (median 2,
90th percentile 18), so the archive starts there.

### Each year's most cited tenth (decision 22, 2026-10-21)

The budget's threshold rises while a classic's citations slow down: it kept 8 papers of
2010. A fixed number a year would take every paper of those small years (291 in 2010), and
the budget's share of each year would drop papers of 2015 to 2021 cited 140 to 400 times
for recent ones cited 18 to 40 times. Hence both: the budget, and each year's top tenth,
as bibliometrics compare a paper with its year (Web of Science's highly cited papers are
the top 1% of their field and year). The floor adds about 140 papers, nearly all of 2010
to 2013. Years younger than three get none: their counts still move.

OpenAlex was rejected for the catalog and the counts: its "Computer Vision and Pattern
Recognition" subfield held 48% of the stored cs.CV papers, and it counts a preprint apart
from its published version (Semantic Scholar's counts are 1.7 times higher in median).

## The most cited papers of the last 12 months (`top-recent.json`, PROD-11)

The archive starts at 12 months and the day files began in September 2026 (decision 1).
The weekly run counts every catalog paper anyway and keeps the 1,000 most cited of the
last 12 months apart, for Highly cited's "Last 12 months" (a year of cs.CV is 46,000).

- **Selection** (`select_top_recent`): papers first seen within 12 months (`is_recent`),
  withdrawn and never-cited ones excepted, by citations per month of age counting at least
  two (`TOP_RECENT_MIN_MONTHS`); the best 1,000 (`TOP_RECENT_BUDGET`). Per year of age
  would rank them by raw counts (none of August among 623 in September); over one month,
  two early citations (often the authors' next paper) would rank a paper with the best.
- **Records**: a day-file paper is its record there, on its day; one kept from last week
  keeps its record, comments refreshed; the others are built from the catalog as archived
  papers are. A paper without a count this week keeps last week's.
- **Writing**: `since` is 364 days before the run; the file is rewritten whole and listed
  in the index. It holds no archived paper (same window, same first appearance). Every
  OpenAlex lookup comes before the first write, and the list is written before the
  archive, so a run stopped between writes leaves no paper in both. `validate` fails a
  file that does not load, a paper listed twice, announced before `since` or archived,
  and an index that disagrees.
- Steps on every stored paper include them (`citations ALL=1`, `scholar`, `venues`,
  `institutions-again`, `code`, `countries`). A paper that ages out enters the archive
  only if it ranks there, with the record it had, never rebuilt from the catalog.

## Citation counts (`citations.json`)

- Semantic Scholar's (`paper/batch`, 500 ids a request, all versions counted), out of the
  records so that a refresh rewrites one file. The archive rewrites it, dated
  (`write_citations`); the daily `citations` step adds the new papers' counts, keeping the
  date (`merge_citations`). A paper not known yet gets none and is asked the next day.
- Counts are cached 7 days (`CITATIONS_CACHE_DAYS`) in
  `.cache/catalog/<category>.citations.jsonl`, so a stopped run resumes: `generated_at` can
  postdate some by up to 6 days. Older than 14 days, they are reported stale.
- **Gains** (`citation-gains.json`, CIT-9): a full refresh writes what each paper gained
  over the counts it replaces when those are at least 6 days old (`GAINS_MIN_DAYS`), else
  keeps the week's. A drop is no gain; a paper counted only by the daily step gains from
  that count. `validate` fails a file that does not load and warns of papers no longer
  stored; `commit-data.sh` keeps the run's counts and gains on a conflict.

## Published versions (`scholar.json`)

- The weekly `scholar` step (after the archive) asks Semantic Scholar for every stored
  paper (about 26,000 in 52 requests): the published version's DOI (never arXiv's
  `10.48550/...`), its venue (`venue.published_venue`, [extraction.md](extraction.md)) and
  the authors' ids.
- Ids are kept only when it lists as many authors as the paper, each only where its name
  is the arXiv author's at that place (`collect.checked_author_ids`, AFF-H): it merges
  versions and lists some authors swapped or shifted. A name matches when one spelling
  holds the other's words (accents folded, hyphens joined) or by surname and first
  initial. The names are never stored.
- The file is rewritten whole (`collect.update_scholar_records`); a paper it kept refusing
  keeps last week's record. `validate` fails a file that does not load, warns on stale ones.
- The build merges DOI, venue and ids into the site's records ([web.md](web.md)). It has
  a venue for 90% of the archive but 5% of recent papers, so the comments' comes first.

## Semantic Scholar's moods

- One request every 1.1 s with `SEMANTIC_SCHOLAR_API_KEY` (a repository secret), 2 s
  without. Even with a key, about half the batches are refused in CI.
- A refused batch (429, a 5xx, any failure but those below) is tried again after 2 s (20 s
  without a key), doubled up to 60 s, 30 times (about 25 minutes), or after its
  `Retry-After`, within five minutes (CIT-8). After 30 refusals the fetch stops, the rest
  left for the next run. The last log line counts the refused tries and the Retry-Afters.
- `400 No valid paper ids given` means it knows none of the batch: those papers are
  unknown, not refused, and not tried again in the run (CIT-17).
- A 401 or 403 is a bad key (the 429 message's advice to get one says nothing of it): the
  first stops the fetch with "Semantic Scholar rejected the API key" and fails the run.
- An answer that is not one entry per paper asked for is tried twice
  (`S2_MISMATCH_TRIES`), then asked in halves down to the paper it cannot answer for, left
  out (`cannot answer for`; about 10 requests for one in 500). Past 50 such batches
  (`S2_MAX_MISMATCHED_BATCHES`), the fetch stops.
- Time limits (`--max-minutes`): 10 for the daily `citations`, 20 for the weekly `scholar`.
- Retries live in `_fetch_batch` and `_fetch_all` (counts and records alike), whose
  `HttpClient` makes one attempt; refusals log at debug level, streaks of 5 at INFO.

## OpenAlex

- `works?filter=doi:10.48550/arxiv.<id>|...`, 50 a request, one every 0.25 s; the works the
  filter misses are asked one by one by DOI. A failed batch waits for the next run.
- Its institutions per author are registry entries: they are the paper's affiliations and
  `institutions`, with ROR ids, provenance `openalex` and the lookup's day. Its raw strings
  are too rough, and OAI's `<affiliation>` is never filled (AFF-19).
- It learns recent papers over months (affiliations for 16% of the archive's 2025 papers,
  48% of 2024's, 60% before): one it knew nothing of is asked again every 30 days
  (`OPENALEX_RETRY_EVERY_DAYS`) while under two years old (`OPENALEX_RETRY_AGE_DAYS`),
  from its last lookup, or at once when that day is unknown (AFF-3, decision 5).
- Day-file papers without an HTML page (about 5%), or whose page gave none, a month after
  (AFF-31), are asked daily (`make affiliations`, AFF-27), then every 30 days. Registry
  names, their affiliations are left alone by `reclean`, `validate`'s heuristics and
  `quality-affiliations`.
- Papers whose OpenAlex affiliations predate the ids are asked again by the archive; those
  it now gives nothing keep theirs, without ids, and are asked each week.
- **Countries** (`make countries`, UX-40): `/institutions` by ROR id, 50 a request, only
  for the ids `countries.json` lacks (`ALL=1`: all). `null` (placed nowhere) is kept and
  not asked again; a failed batch is asked next time; ids of no stored paper leave.

## Affiliations of the highly cited papers (`archive-affiliations`)

By arXiv DOI, OpenAlex left about half the archive without affiliations, and 84% of 2025's
papers. `collect.update_archive_affiliations` fills those of the archive and of top-recent
(not the day files') two ways:

- **The published version** (AFF-20; weekly, after `scholar`): OpenAlex's record of the
  DOI in `scholar.json`, 50 a request, two minutes the first time. Each arXiv author takes
  the institutions of the published author of the same name (`names.same_person`); fewer
  than half found means a wrong DOI, and nothing is taken. A paper it gives nothing is
  asked again each week, as is a DOI learned later.
- **The HTML page** (AFF-28, `MAX_HTML=N`): the papers still without any that arXiv
  renders (since December 2023, the first version) or, before, ar5iv (AFF-37, arXiv
  Labs: the same LaTeXML, the latest version, `archive_page_url`; its `robots.txt` only
  disallows `/log/`; 1,735 of the 2,362 highly cited papers without affiliations on
  2026-10-28, Mask R-CNN's "Facebook AI Research (FAIR)" among them), the most cited first, read as the
  daily update reads pages (15 s each, the same stops), from the cache when it holds them.
  A 404 leaves `<id>v1.html.missing`, never asked again. A page that gives nothing stays
  cached and is not read again while today's extraction finds nothing in it (read first,
  such pages would stop the run as a layout change), unless `PageCache.stale`. Its
  affiliations come with its `html_url`, the extractor's version and provenance `html`;
  ROR names their institutions, and those an interrupted run left unnamed. The maintainer
  runs it (a night for about 2,000 papers), not a workflow, whose minutes are billed.
  `reextract` never reads the archive: later extraction fixes reach it only this way;
  `reclean` cleans its papers read from a page again (provenance `html`, never OpenAlex's
  names), whose institutions this step names again.

## Stars of the papers' code (`code.json`, PROD-18)

- **The link** is the card's (`code.py`, a port of `web/src/code.ts` and `linkify.ts`,
  both tested on `tests/fixtures/code-cases.json`): the first GitHub or GitLab repository
  in the abstract or comments, else a Hugging Face model, dataset or demo. About 29% of
  the papers link GitHub, one in 400 the Hub; GitLab is not asked.
- **GitHub** (`sources/github.py`): GraphQL, 100 repositories a query (aliases), one point
  of the hourly quota each, with any token (`GITHUB_TOKEN`: the workflow's in CI, 1,000
  points an hour; `.env`'s for `make code` only); REST's 60 anonymous requests an hour
  would take days. A `NOT_FOUND` alias (deleted, private, never published) drops the
  paper's record; any other error fails the query, whose papers keep last week's; a 401
  fails the run.
- **Limits**: secondary limits cap GraphQL's CPU time at 60 s a minute, about 2 s a query
  (one a second was refused after 30), so one every 3 s (`GITHUB_DELAY_SECONDS`), about 5
  minutes a run. A 403 or 429 waits for its `Retry-After`, else a minute, then two; refused
  a third time (`GITHUB_LIMIT_TRIES`), the run stops asking, the rest keep last week's.
- **The Hub** (`sources/huggingface.py`): `/api/models/<id>` (or `datasets`, `spaces`),
  one request every 0.5 s, no key: its `likes`, apart from stars. A 401 or 404 means the
  page is gone (401 also for one that never existed).
- **`shared`**: a repository several stored papers link, or a link into a folder of one
  (`/tree/<branch>/<folder>`, a file below the root; `/tree/<branch>` alone or a root file
  is the repository). Shown as shared; Most starred ranks them with the unstarred papers.
- **Gains** (`PaperStore.write_code`): from the file it replaces, as the citations'
  (`GAINS_MIN_DAYS`), kept through a second run in the week; none for a changed link.
- **Weekly**, `archive.yml` runs `code` after `scholar`: every stored paper, once.
  **Daily**, `update.yml` runs `code --new` (`NEW=1`): only the papers without a record
  (new since Sunday, or a repository GitHub did not know), a query or two. The others keep
  their record and gains, the file Sunday's date (`PaperStore.add_code`: a later one would
  make Sunday's refresh keep gains instead of counting them); `shared` is worked out again.

## OAI-PMH

`oaipmh.arxiv.org`, set `cs:cs:CV`: arXiv's sanctioned bulk metadata. No crawl delay in its
robots.txt; 5 s between pages, about 45 minutes for the whole set. `created` is not always
the first version's date.
