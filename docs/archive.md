# The citation archive and the scholarly sources

How the weekly archive (`archive/`), the citation counts, the published versions and the
stars of the papers' code work, and what Semantic Scholar, OpenAlex, arXiv's OAI-PMH,
GitHub and the Hugging Face Hub are like to work with. Read this before changing
`archive/`, `sources/semantic_scholar.py`, `sources/openalex.py`, `sources/arxiv_oai.py`,
`sources/github.py` or `sources/huggingface.py`. The failures and what to do about them are in [operations.md](operations.md).

## The weekly archive (`archive/update.py`, `archive.yml`, Sundays)

- `archive/catalog.py` keeps the category's OAI-PMH set, harvested by
  `sources/arxiv_oai.py`, in `.cache/catalog/` (git-ignored; the Actions cache in CI).
- `sources/semantic_scholar.py` gets a citation count for every candidate (about 207,000,
  in 415 requests).
- `archive/selection.py` ranks the papers older than 12 months by citations per year of
  age (`max(age, 1)`) and keeps a budget of them: 22,000 by default, about 20 citations a
  year. An archived paper leaves only beyond 1.15 times the budget.
- `sources/openalex.py` gives the affiliations of papers that enter from the catalog:
  OpenAlex's institutions, which are registry entries, so they are also the papers'
  `institutions`, with their ROR ids, and both have the provenance `openalex` and the day
  of the lookup (the day a paper OpenAlex knew nothing of can be asked again, AFF-3).
- Day-file papers compete too, once first seen 12 months ago (the earlier of their day
  file and the catalog's date, which can be weeks later: 2609.00036 was announced on
  2026-09-02, the catalog says 2026-09-14). They enter with their own enrichment, filed
  under that first appearance: an old paper cross-listed lately goes to its own year.
- Every stored paper, day files and archive alike, takes the comments and journal
  reference of its latest version from the catalog, and the venue they give (META-2,
  `refreshed`): a record otherwise keeps what the listing said when it was announced
  ("Under review" long after its acceptance). The catalog never empties a field. This
  needs a catalog just harvested, so it only runs within the weekly update, even when
  the citation counts fall short.
- A withdrawn paper (`withdrawn`, from the comments of its latest version) is never a
  candidate, and an archived one leaves (decision 18). `withdrawal.is_withdrawn` reads 467
  of the catalog's 473 comments that mention a withdrawal as one; the 6 others are
  withdrawals from a workshop or the proceedings, of an earlier version or of another
  submission.
- Deleting day files older than 12 months (`--prune`) keeps a rolling year of day files
  (decision 2): `archive.yml` prunes since 2026-10-06 (the `PREPRINT_RADAR_ARCHIVE_PRUNE`
  repository variable), which deletes nothing before September 2027. It decides nothing
  else: an archived paper can also be in a day file.
- With less than 95% of citation counts, the archive and day files stay as they are (their
  comments are refreshed all the same), the
  counts fetched are merged into `citations.json`, whose date stays, and the command fails
  once it has written them (`archive.yml` validates and commits even then). Above it, an
  archived paper whose count is missing this week is ranked on last week's.
- Archived records: `announced` is the first appearance (from the identifier's month when
  OAI's `created` disagrees), `html_url` is `null` for a paper built from the catalog; one
  that enters from a day file keeps that record, its HTML link and affiliations with it.
- A paper built from the catalog names its subjects as the listings do: as the day files
  name the code, else from arXiv's taxonomy (`archive/subjects.py`, META-8), where an
  alias is its canonical subject, listed once (OAI gives `eess.SY cs.SY`, the listings
  "Systems and Control (eess.SY)"); a code neither knows stays bare. Its authors are
  arXiv's metadata without what the author list added (`arxiv_oai.author_names`,
  AFF-21): trailing footnote digits, `*` and `†` ("Jie Qin1"), a leading "and ", and the
  author "others" ("et al."). The catalog is cleaned as it is read, so the cache
  harvested before needs no new harvest. Both apply to the papers entering the archive:
  archived records keep their names and subjects until a one-off rewrite, and day files
  keep the names the listing gives (a starred one in 2610.05756).

## Why citations per year of age (the calibration of September 2026)

The archive's rule and its default budget come from a study of every cs.CV paper since 2010
made on 2026-09-29: arXiv's OAI-PMH set `cs:cs:CV` (206,740 papers, cross-lists included)
and Semantic Scholar's counts (99.6% found). Its scripts and their 22 MB of data stay
local, in the git-ignored `experiments/2026-09-citations/` (DOC-4); its findings are these.

A fixed threshold favors old papers: 500 citations keep 486 papers of 2018 but 64 of 2025.

| Citations at least | Papers | Primary cs.CV | Cross-lists |
| ---: | ---: | ---: | ---: |
| 500 | 3,559 | 2,942 | 617 |
| 1,000 | 1,484 | 1,223 | 261 |
| 5,000 | 192 | 159 | 33 |
| 10,000 | 81 | 67 | 14 |
| 100,000 | 3 | 3 | 0 |

Citations per year of age compare old and recent papers fairly. Over the 160,466 papers
older than a year:

| Citations a year at least | Papers | Older than 5 years |
| ---: | ---: | ---: |
| 10 | 41,537 | 15,980 |
| 20 | 22,619 | 9,385 |
| 50 | 8,252 | 3,710 |
| 100 | 3,440 | 1,634 |

Hence the budget of 22,000, about 20 citations a year, which rises with the field instead
of a threshold to move by hand. A paper of 12 months has few (6,141 papers of
2025-08-15 to 2025-10-15: median 2, 90th percentile 18, 99th 109; 20 or more keeps 9%),
so the archive takes papers older than 12 months, and the last 12 months rank by
citations per month of age (PROD-11, below). At about 2.5 KB a paper in JSON, the budget
weighs about 55 MB.

OpenAlex was rejected for both questions. Its subfield "Computer Vision and Pattern
Recognition" is not cs.CV: it held 48% of the papers stored in September 2026 (51% of
primary cs.CV papers, 35% of cross-lists), and 59% of the arXiv works it put there
(2026-09-01 to 18) were in cs.CV. It counts a preprint apart from its published version:
Semantic Scholar's counts were 1.7 times higher in median over 18 papers, up to 6 times
(DDPM) and 13 times (YOLOv7). The catalog comes from arXiv, the counts from Semantic
Scholar.

## The most cited papers of the last 12 months (`top-recent.json`, PROD-11)

The archive starts at 12 months, and the day files began in September 2026 (decision 1): the
papers first seen from October 2025 to August 2026 were in no file. The weekly archive has
their counts anyway (it asks for every paper of the catalog), and keeps the most cited of
them apart, in `<category>/top-recent.json`, which the site offers as Highly cited's "Last
12 months". Once the day files hold a year, the list stays: a view loads 10,000 papers, a
year of cs.CV is 46,000.

- `archive/selection.py`, `select_top_recent`: the papers first seen within the last 12
  months (`is_recent`, the window the archive leaves out), withdrawn and never-cited ones
  excepted, ranked by citations per month of age, counting at least two months
  (`config.TOP_RECENT_MIN_MONTHS`); the best 1,000 (`TOP_RECENT_BUDGET`). The archive's
  score, per year of age counting at least one, would rank them by their raw counts: of the
  623 papers at its threshold in September 2026, 6 were from July and none from August. Per
  month of age from 80 to 180 papers a month enter, but 50, 29 and 25 for the last three
  (the newest have had no time; the day files hold them), and the least cited have 4.
  Counted over one month, two citations in a paper's first weeks (often its authors' next
  paper) would rank it with the best of the year.
- Records: a paper of the day files is its record there as the run reads it, on its day
  (the catalog's date, its first version's, is often a day or two earlier, and the site
  links it to its day); one kept from last week keeps its record (its OpenAlex
  affiliations), with the comments of its latest version; the others are built from the
  catalog, with affiliations from OpenAlex, as archived papers are (`_with_affiliations`,
  which asks again for those it knew nothing of every 30 days). OpenAlex knows the
  affiliations of few recent preprints, about one in six in 2025, more by their published
  version, and their pages give the others' (`archive-affiliations`, below). A paper
  Semantic Scholar misses this week keeps last week's count, as an archived one.
- The file has the first day of the window (`since`, 364 days before the run) and is
  rewritten whole; the index lists it (`top_recent`: `since` and `count`). It holds no
  archived paper: both use the same window and first appearance. Below the coverage gate,
  last week's papers stay, with their comments refreshed. Every OpenAlex lookup comes
  before the first write, and the list is written before the archive (last week's may hold
  papers entering it, this week's none it held): a run stopped between two writes leaves
  no paper in both, which `validate` would refuse.
- Every step on "every stored paper" includes them: the counts (`citations`, `ALL=1`), the
  published versions (`scholar`), `make venues` and `make institutions-again`. `validate`
  fails a file that does not load, a paper listed twice, announced before `since` or
  archived too, and an index that disagrees with it.
- A paper that ages out leaves at the next run; it enters the archive only if it ranks
  there, with the record it had (its day file's, or this list's, with what its published
  version or its page gave), never built again from the catalog.

## Citation counts (`citations.json`)

- Semantic Scholar (`paper/batch`, 500 arXiv ids a request) counts all versions of a
  paper. OpenAlex undercounts published papers (×1.7 in median), so it is not used for
  counts.
- `citations.json` holds the counts of every stored paper, day files, archive and the most
  cited of the last 12 months alike, out of the paper records so that the weekly refresh
  rewrites one file, not every day file. The weekly archive rewrites it (`write_citations`,
  dated); the daily `citations` step adds the counts of new papers (`merge_citations`,
  which keeps the date of the last refresh). Papers Semantic Scholar does not know yet (a
  few days) get no count and are asked for again the next day.
- Counts are cached in `.cache/catalog/<category>.citations.jsonl` (restored with the
  catalog in CI) and reused for 7 days, so a failed or cancelled run resumes where it
  stopped: `citations.json`'s `generated_at` can postdate some counts by up to 6 days.
- Counts older than 14 days are reported as stale, in `stats` and on the site.
- Each full refresh (`write_citations`) also writes `citation-gains.json` (CIT-9): what
  each paper gained since the counts it replaces, for the site's rising papers. Only from
  counts at least 6 days old (`config.GAINS_MIN_DAYS`), so that a refresh run again within the
  week keeps the week's gains; a count that went down is no gain, and a paper counted
  since only by the daily step gains from that count. The first gains are those of the
  archive of 2026-10-11: the run of 2026-10-04 reused the cached counts of 2026-09-30.
  `validate` fails a gains file that does not load, and warns of gains of papers no
  longer stored; `commit-data.sh` keeps the run's gains on a conflict, as its counts.
- The site loads them in shards built from `citations.json` ([web.md](web.md)).

## Published versions (`scholar.json`)

- The weekly `scholar` step (after the archive in `archive.yml`; `make scholar`) asks
  Semantic Scholar for every stored paper (about 26,000 in 52 requests, minutes with a
  key): the DOI of the published version (not arXiv's `10.48550/...`), its venue, named by
  `venue.published_venue` (see [extraction.md](extraction.md)), and the authors' ids, kept only when
  Semantic Scholar lists as many authors as the paper, and each only where the name it
  gives is the arXiv author's at that place (`collect.checked_author_ids`, AFF-H): Semantic
  Scholar merges versions and papers, and lists some in another order (2303.17912, two
  authors swapped; 2505.11594, shifted by one). A name is the author's when one spelling
  holds the other's words ("Mahdi S. Hosseini"), hyphenated given names joined
  ("Jin-Chao Zhang") and letters folded ("Kalaycıoğlu"), or with the same surname and first
  initial ("D. Gopinath"). The names are never stored.
- `collect.update_scholar_records` rewrites the file: a paper Semantic Scholar was not
  asked for (it kept refusing) keeps last week's record, and papers no longer stored are
  dropped. `validate` fails a file that does not load, and only warns on stale records.
  `stats` counts its venues with the detected ones.
- The store keeps it apart from the records, since it changes every week; the build
  merges the DOI, the venue and the authors' ids into the records the site serves
  ([web.md](web.md)).
- Semantic Scholar has a venue for about 90% of the archive (52% from comments), and for
  5% of recent papers (19% from comments), so the comments stay first for those.

## Semantic Scholar's moods

- Even with `SEMANTIC_SCHOLAR_API_KEY` (a repository secret, one request per second),
  about half of the batches were refused (429) in CI. A refused batch is tried again after
  2 s, doubled up to 60 s (20 s at first without a key, whose shared pool is busier), 30
  times; a refusal with a `Retry-After` is waited for as it asks instead, within five
  minutes (`FetchError.retry_after`, CIT-8). Whether Semantic Scholar sends one is not
  known yet: the run's last line counts them ("…, 12 refused tries, 0 with a
  Retry-After"). The retries live in `_fetch_batch` and `_fetch_all`, shared by
  `fetch_citation_counts` and `fetch_scholar_records`: their `HttpClient` makes a single
  attempt. Refusals are logged at debug level; only streaks of 5 reach the INFO log, and
  progress every 5,000 papers.
- The 429 message suggests applying for a key even to keyed requests: it says nothing
  about the key. An invalid key gets `403 Forbidden` on every request, so a run that makes
  progress has a valid one: the first 401 or 403 stops the fetch with "Semantic Scholar
  rejected the API key", which fails the run (`FetchError.status`).
- The daily `citations` step gives a refusing Semantic Scholar 10 minutes
  (`--max-minutes`), the weekly `scholar` step 20, then leaves the papers for later.
- An answer that is not one entry per paper asked for (a JSON object, a shorter list) is no
  refusal: on 2026-10-11 one batch got it 30 times over 25 minutes, and the 1,415 papers
  from it on got no count that week. It is tried twice (`S2_MISMATCH_TRIES`), then asked
  for in halves (`_fetch_all`), down to the paper Semantic Scholar cannot answer for, left
  out with what it answered in the log (`cannot answer for`); about 10 requests for one
  such paper among 500. Past 50 such batches in a run, it stops as for refusals.

## OpenAlex

- `works?filter=doi:10.48550/arxiv.<id>|...`, 50 a request; the DOI filter misses some
  works that the DOI lookup finds, so those are asked for one by one.
- Its institutions per author are used; its raw affiliation strings are too rough.
- It learns the institutions of recent papers over months: of the archive's papers first
  seen in 2025, 16% had affiliations, in 2024 48%, against about 60% for older years. An
  archived paper it knew nothing of is asked again every 30 days
  (`OPENALEX_RETRY_EVERY_DAYS`) while under two years old (`OPENALEX_RETRY_AGE_DAYS`),
  counted from the day of its last lookup (`provenance`), or at once when that day is
  unknown; the log says how many of them have affiliations now (AFF-3, decision 5).
- The papers of the day files that arXiv has no HTML rendering of (231 of 4,832 in
  October 2026: it could not convert their LaTeX, and the abstract page lists names only)
  are asked for too, daily (`collect.update_openalex_affiliations`, `make affiliations`,
  AFF-27): two in five a month old have affiliations, 94 of 225 the first day; the others
  are asked again every 30 days, as archived papers (`openalex_affiliations.py`, shared with
  the archive). Their affiliations are OpenAlex's registry names, so `reclean`, `validate`'s
  heuristics and `quality-affiliations` leave them alone, as the archive's.
- Its institutions carry ROR ids. Archived papers whose affiliations came from OpenAlex
  before ids were kept (their institutions are their affiliations) are asked for again,
  once, by the weekly archive; those it now gives nothing for keep their affiliations
  without ids and are asked for again every week (a few requests).

## Affiliations of the highly cited papers (`archive-affiliations`)

By their arXiv DOI, OpenAlex left 10,520 of the archive's 22,169 papers without
affiliations in October 2026, 84% of those first seen in 2025, the year Highly cited
shows first. `collect.update_archive_affiliations` (`make archive-affiliations`) fills
those of the archive and of the last 12 months (but the day files' papers there, whose
records are their day records) two ways:

- **The published version** (AFF-20): OpenAlex knows the authors and institutions of
  nearly every published version, by the DOI Semantic Scholar gives (`scholar.json`, not
  arXiv's own `10.48550/...`): `sources/openalex.fetch_published_authors`, 50 DOIs a
  request, 142 requests and two minutes for the 7,076 papers with one. Its authors can be
  others or in another order, so each arXiv author takes the institutions of the published
  author of the same name (`names.same_person`: one spelling holding the other's words, or
  the surname and first initial), and fewer than half of them found means another paper
  (a wrong DOI, 24 of 7,027): nothing is taken. A spike on 49 such papers gave 46; the
  first run 6,799, every author placed for 84% of them (the others: OpenAlex places only
  some authors of that version). The archive went from 53% to 83% with affiliations, 2025
  from 16% to 51%, 2024 from 48% to 73%. `archive.yml` runs it after `scholar`, whose DOIs
  it reads, every week: a paper it gives nothing yet is asked for again then (a few
  requests), and a DOI Semantic Scholar learns later is asked for the next week. The
  affiliations have the provenance `openalex`, as the arXiv DOI's.
- **The HTML page** (AFF-28), with `--max-html N` (`MAX_HTML=N`): the papers still
  without any that arXiv renders (submitted since December 2023,
  `arxiv_html.first_version_url`, the first version, which a day file links to), the most
  cited first, read as the daily update reads pages (`_add_html_front_matter`: 15 s a
  page, the same stops), from the page cache when it holds them. A page that answers 404
  leaves `<id>v1.html.missing` in the cache and is never asked for again; one that gives
  nothing leaves the paper as it was, its page cached, and is not read again while
  today's extraction finds nothing in it: read first, since cached, 349 such pages stopped
  the second run as a layout change (2026-10-12). A stale page (`PageCache.stale`) is
  read again all the same. A paper its page gives
  affiliations takes them with the page's link (`html_url`), the extractor's version and
  the provenance `html`; their institutions are named through ROR, with those an
  interrupted run left unnamed. About 2,000 papers of 2024 and 2025 are left after the
  published versions, a night of downloads: the maintainer runs it
  (`docs/operations.md`), not a workflow, whose minutes are billed. A spike on 4 such
  pages gave 3. Neither `reextract` nor `reclean` reads the archive: a later extraction
  fix reaches these papers only through this command, for those without affiliations.

## Stars of the papers' code (`code.json`, PROD-18)

- The link is the one the card shows (`code.py`, a port of `web/src/code.ts` and
  `linkify.ts`; `tests/fixtures/code-cases.json` holds the cases both test suites read):
  the first repository on GitHub or GitLab in the abstract or comments, else a model,
  dataset or demo on the Hugging Face Hub. In October 2026, 7,834 stored papers of 27,000
  link GitHub (7,541 repositories), 65 the Hub, 6 GitLab (not asked for).
- `sources/github.py`: GitHub's GraphQL API, 100 repositories a query (aliases of
  `repository { stargazerCount }`), one point of the hourly quota each: 76 queries, one
  every 3 s, about 5 minutes with the Hub's 63 pages at 0.5 s. It needs a token, any, even
  one without permission (`GITHUB_TOKEN`: the
  workflow's own in CI, which allows 1,000 points an hour; the Makefile gives `.env`'s to
  `make code` only). The REST API's 60 anonymous requests an hour would take days. A
  repository deleted, made private or never published comes back as its alias's
  `NOT_FOUND` error (3 of 100 sampled): the paper loses its record. Any other error fails
  the query, whose papers keep last week's records; a 401 is a bad token and fails the run.
- GitHub's secondary limits cap the CPU time of GraphQL queries, 60 s a minute, and one of
  100 repositories takes about 2 s: at one a second, the first run in CI (2026-10-11) was
  refused (403, "You have exceeded a secondary rate limit") after 30 queries, and 4,698
  papers kept the stars of 2026-10-09. Queries go one every 3 s (`GITHUB_DELAY_SECONDS`,
  from the start of one to the next), and one refused for a limit (403 or 429) waits for
  its `Retry-After` (`FetchError.retry_after`), else a minute, then two, as GitHub advises;
  refused a third time, the run stops asking and the rest keep last week's records.
- `sources/huggingface.py`: the Hub's `/api/models/<id>` (or `datasets`, `spaces`), one
  request each, without a key: its `likes`, kept apart from the stars. A 401 or 404 means
  the page is gone (the Hub answers 401 for one that never existed).
- `shared`: a repository more than one stored paper links (`google-research/
  google-research` 19 papers, `big_vision` 9, `mmdetection` 8), or a link into a folder of
  one (`/tree/<branch>/<folder>`, or a file below the root: 116 links);
  `/tree/<branch>` alone, or a file at the root, is the repository. In October 2026, 478
  papers share their repository with another stored paper (a lab's toolbox, a paper and its
  extension). Their stars show, said shared, and Most starred ranks them with the papers
  without stars.
- Gains: `PaperStore.write_code` counts each paper's stars gained from the file it
  replaces, as the citations' (`GAINS_MIN_DAYS`), and keeps them through a second run in
  the week; a paper whose link changed gained nothing yet. The first gains come a week
  after the first file.
- `archive.yml` runs `code` every week after `scholar` (`GITHUB_TOKEN: ${{ github.token }}`):
  every stored paper is asked for, the day files, the archive and the most cited of the
  last 12 months, each once.
- `update.yml` runs `code --new` every weekday after `citations` (`NEW=1` locally): only
  the papers without a record of their link, those announced since Sunday (34 on
  2026-10-09, which waited up to a week before) and those whose repository GitHub did not
  know (117 of 7,939 papers linking code, a 404 for each of 12 sampled: code announced
  before it is public, or a typo of the abstract), a query or two. The others keep their
  record and gains, and the file the date of Sunday's refresh (`PaperStore.add_code`):
  written dated that day, it would leave Sunday a file less than `GAINS_MIN_DAYS` old,
  whose gains it keeps instead of counting them. Only `shared` is worked out again, since
  a new paper may link a repository already stored.

## OAI-PMH

`oaipmh.arxiv.org`, set `cs:cs:CV`: arXiv's sanctioned bulk metadata. No crawl delay in its
robots.txt; 5 s between pages, about 45 minutes for the whole set. `created` is not always
the first version's date.
