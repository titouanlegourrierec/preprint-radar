# The citation archive and the scholarly sources

How the weekly archive (`archive/`), the citation counts and the published versions work,
and what Semantic Scholar, OpenAlex and arXiv's OAI-PMH are like to work with. Read this
before changing `archive/`, `sources/semantic_scholar.py`, `sources/openalex.py` or
`sources/arxiv_oai.py`. The failures and what to do about them are in [operations.md](operations.md).

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
  OAI's `created` disagrees), `html_url` is `null`.

## Citation counts (`citations.json`)

- Semantic Scholar (`paper/batch`, 500 arXiv ids a request) counts all versions of a
  paper. OpenAlex undercounts published papers (×1.7 in median), so it is not used for
  counts.
- `citations.json` holds the counts of every stored paper, day files and archive alike,
  out of the paper records so that the weekly refresh rewrites one file, not every day
  file. The weekly archive rewrites it (`write_citations`, dated); the daily `citations`
  step adds the counts of new papers (`merge_citations`, which keeps the date of the last
  refresh). Papers Semantic Scholar does not know yet (a few days) get no count and are
  asked for again the next day.
- Counts are cached in `.cache/catalog/<category>.citations.jsonl` (restored with the
  catalog in CI) and reused for 7 days, so a failed or cancelled run resumes where it
  stopped: `citations.json`'s `generated_at` can postdate some counts by up to 6 days.
- Counts older than 14 days are reported as stale, in `stats` and on the site.
- The site loads them in shards built from `citations.json` ([web.md](web.md)).

## Published versions (`scholar.json`)

- The weekly `scholar` step (after the archive in `archive.yml`; `make scholar`) asks
  Semantic Scholar for every stored paper (about 26,000 in 52 requests, minutes with a
  key): the DOI of the published version (not arXiv's `10.48550/...`), its venue, named by
  `venue.published_venue` (see [extraction.md](extraction.md)), and the authors' ids, kept only when
  Semantic Scholar lists as many authors as the paper, since they are matched by position.
- `collect.update_scholar_records` rewrites the file: a paper Semantic Scholar was not
  asked for (it kept refusing) keeps last week's record, and papers no longer stored are
  dropped. `validate` fails a file that does not load, and only warns on stale records.
  `stats` counts its venues with the detected ones.
- The store keeps it apart from the records, since it changes every week; the build
  merges the DOI and the venue into the records the site serves ([web.md](web.md)).
- Semantic Scholar has a venue for about 90% of the archive (52% from comments), and for
  5% of recent papers (19% from comments), so the comments stay first for those.

## Semantic Scholar's moods

- Even with `SEMANTIC_SCHOLAR_API_KEY` (a repository secret, one request per second),
  about half of the batches were refused (429) in CI. A refused batch is tried again after
  2 s, doubled up to 60 s (20 s at first without a key, whose shared pool is busier), 30
  times. The retries live in `_fetch_batch` and `_fetch_all`, shared by
  `fetch_citation_counts` and `fetch_scholar_records`: their `HttpClient` makes a single
  attempt. Refusals are logged at debug level; only streaks of 5 reach the INFO log, and
  progress every 5,000 papers.
- The 429 message suggests applying for a key even to keyed requests: it says nothing
  about the key. An invalid key gets `403 Forbidden` on every request, so a run that makes
  progress has a valid one: the first 401 or 403 stops the fetch with "Semantic Scholar
  rejected the API key", which fails the run (`FetchError.status`).
- The daily `citations` step gives a refusing Semantic Scholar 10 minutes
  (`--max-minutes`), the weekly `scholar` step 20, then leaves the papers for later.

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
- Its institutions carry ROR ids. Archived papers whose affiliations came from OpenAlex
  before ids were kept (their institutions are their affiliations) are asked for again,
  once, by the weekly archive; those it now gives nothing for keep their affiliations
  without ids and are asked for again every week (a few requests).

## OAI-PMH

`oaipmh.arxiv.org`, set `cs:cs:CV`: arXiv's sanctioned bulk metadata. No crawl delay in its
robots.txt; 5 s between pages, about 45 minutes for the whole set. `created` is not always
the first version's date.
