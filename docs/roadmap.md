# Roadmap

Progress on the improvements found by the audit of 2026-09-30
([`audit/2026-09-30.md`](audit/2026-09-30.md)). The audit is a frozen snapshot: its item IDs
(`DATA-2`, `SRCH-1`…) name its cards and tables, and its line numbers describe commit `e565fbe`.
This file is the living part.

- Update an item's status in the commit that changes it, and name the ID in the commit
  message, e.g. `fix(collect): reset the author mapping when the author list changes (DATA-2)`.
- Status: `todo`, `done` (with the commit), `dropped` (with the reason).
- Priorities are the audit's, after verification. Items outside the phases below stay in the
  audit's §18 backlog: pick them up when touching the same code.
- After each phase, run `make stats` (and `validate` once it exists) and note the result under
  the phase.

## Corrections to the audit

The audit stays frozen: facts found wrong later are recorded here, and the phases below follow them.

- **CI-1 (2026-10-01).** The audit says no run had been lost to a rebase conflict, and lowers CI-1
  to P2 on that ground. The scheduled run of 2026-09-28 (Actions run 36407146351) was lost exactly
  that way: `git pull --rebase` stopped on a conflict in `data/index.json`. CI-1 is P1 again, and
  moves to Phase 0.

## Decisions

The audit's §21 decisions, with its recommendation. *Blocks* names the first item waiting
for the answer.

| # | Decision | Recommendation | Blocks | Answer |
|---|---|---|---|---|
| 1 | Retention and the 11-month gap | Fill the gap from the OAI catalog, after PERF-1 and CIT-11 | PROD-1 | No fill: the project started in September 2026, and the day files grow from there (2026-10-06) |
| 2 | Prune at 12 months | Land CIT-11 first (selection no longer depends on prune), then prune once 12 months exist, after CIT-3 | CIT-11 | CIT-11 accepted (2026-10-01); a rolling year once 12 months exist, from September 2027: pruning is on (`PREPRINT_RADAR_ARCHIVE_PRUNE`, 2026-10-06) and deletes nothing before then |
| 3 | Revised papers (author list changed) | Re-read the HTML, comparing folded names so renames keep their mapping | DATA-2 | Re-read the HTML (2026-10-01) |
| 4 | Where the front-matter cache lives | The Actions cache first, touched daily | DATA-1 (layer 3) | The Actions cache (2026-10-01) |
| 5 | Archive `[]` affiliations | Spike, then retry OpenAlex while young, and say so in the UI | AFF-3 | Retry OpenAlex while young, option A (2026-10-06) |
| 6 | Filter semantics | Exact for clicked names, word prefix for typed text | SRCH-1 | Exact for clicked names, word prefix for typed text (2026-10-03) |
| 7 | Validation strictness | Fail on structural rules, warn on heuristic ones | DATA-3 | Fail on structural rules, warn on heuristic ones (2026-10-01) |
| 8 | License and data terms | MIT for the code; read the Semantic Scholar terms before going public | REL-3 | MIT for the code (2026-10-01); Semantic Scholar's terms checked, its data can be published (2026-10-06) |
| 9 | Visibility, contact and Actions bill | Confirm the private repository with a public site; choose the correction contact | SEC-9 | Correction contact: titouanlegourrierec@kaist.ac.kr (2026-10-01) |
| 10 | Primary persona | The daily cs.CV follower | Phase 2 order | Both, the daily follower and the literature search: Phase 2 goes by priority and dependencies, search first (2026-10-03) |
| 11 | Multi-category | Stay single-category until Phase 3 is done | ARCH-4 | Single-category for now (2026-10-07) |
| 12 | Institution canonicalization | Move the web rules into the pipeline, with ROR ids | AFF-13 | Move the web rules into the pipeline, with ROR ids (2026-10-07) |
| 13 | Author identity | A homonym hint now, Semantic Scholar ids after the META-1 spike | AFF-H | Semantic Scholar author ids (2026-10-07); then, as it has several profiles for most prolific authors, authors keyed by name with a hint where a name's profiles seem several people (2026-10-07) |
| 14 | Graph accessibility target | Rankings as the text equivalent now, the full path later | UX-2 | The full path, with touch zoom (2026-10-06) |
| 15 | Consortium papers in the author projection | Skip the clique above 50 authors; keep AFF-4's current rule | PERF-3 | Skip the clique above 50 authors (2026-10-06) |
| 16 | Failure signalling | Red runs for data-affecting failures, an issue for scheduled runs | CI-2 | Red runs for data-affecting failures (2026-10-01); no issue for now |
| 17 | Math in abstracts | Strip text macros now, lazy KaTeX only if asked | SRCH-19 | Strip text macros, keeping their arguments; no KaTeX (2026-10-07) |
| 18 | Withdrawn papers | Exclude from Highly cited, badge in the day views | META-2 | Exclude from Highly cited, badge in the day views (2026-10-06) |
| 19 | Abstracts by default | On for "Latest day" | Phase 2 | Always collapsed, as now (2026-10-03) |
| 20 | Shipping the audit | Commit it as a frozen baseline | — | Done: `docs/audit/2026-09-30.md` |
| 21 | Versioning | Stay on 0.x; tag a minor release at the end of each phase, with a changelog; 1.0.0 once the public data format is documented and stable | — | Adopted: `v0.1.0` tags the audit commit as the baseline; Phase 4 has no end, so each set of its features is a minor release (2026-10-07) |

## Phase 0: stop publishing wrong data (1–2 days)

| ID | Item | Priority | Status |
|---|---|---|---|
| DATA-2 | Reset the author mapping on author-list changes, enforce the invariants, repair the 2 records | P2 | done |
| AFF-15 | Length guard on `author_affiliations` in the graph | P2 | done |
| AFF-1 | Folded name filter, name lists, IEEE grades (with the consortium exception) | P2 | done |
| AFF-2 | Obfuscated e-mails and brace lists | P2 | done |
| AFF-5 | Junk labels | P2 | done |
| AFF-6 | "Is with" sentences, "also with" | P2 | done |
| DATA-1 | Layer 1: `reclean`, run once over the day files | P1 | done |
| DATA-3 | `validate`, before *Commit data* and in CI | P1 | done |
| DATA-5 | A paper stored once, on its first day (its 2 duplicates failed `validate`) | P2 | done |
| CIT-1 | Merge counts under the gate instead of replacing them | P1 | done |
| CIT-2 | Carry last week's count for archived papers | P1 | done |
| CIT-3 | `min(announced, first_seen)` for graduating papers | P2 | done |
| CIT-11 | Decouple archive selection from pruning | P1 | done |
| CIT-12, CIT-13 | Old papers cross-listed lately: they compete, and enter under their own year (fixed with CIT-11) | P2 | done |
| TEST-1 | `fail_under` (set to 95 by the maintainer; the aim stays 100%) | P2 | done |
| DATA-6 | Write the index right after the first save | P2 | done |
| DATA-7 | Ignore `.tmp` files | P3 | done |
| SEC-9 | About section with a correction contact | P1 | done |
| SEC-10 | Privacy note | P2 | done |
| CI-1 | Robust data commit (raised to P1, see the corrections above) | P1 | done |

*Exit criteria:* `validate` passes with zero structural violations, and the affiliation
quality counts are recorded as a baseline.

*Result (2026-10-01, `v0.2.0`).* `validate`: 26,111 papers in 40 files, 0 errors, 1 warning
(2609.37107: the last author alone holds every affiliation). `make stats` on the day files
(2026-09-01 to 2026-10-01, 4,040 papers): affiliations for 78% of the 3,851 tried, 189 pending;
of the affiliated papers, 89% mapped to their authors and 87% with a named institution. No
affiliation holds a contact detail or only author names (it was 4 and about 70 at the
audit). The archive is unchanged: 22,071 papers, 11,621 affiliated.

## Phase 1: make the pipeline self-healing and observable (about a week)

| ID | Item | Priority | Status |
|---|---|---|---|
| REL-1 | Layout-drift breaker and a weekly network canary | P1 | done |
| REL-2 | HTML deadline, then a consecutive-failure breaker (and REL-6: progress saved on SIGTERM) | P1 | done |
| CI-2 | Run summary and annotations; red runs for data-affecting failures, no failure issue (decision 16) | P1 | done |
| CI-3 | Deploy gating on what was pushed | P2 | done |
| CIT-4 | Stop on a 403, flag stale counts | P1 | done |
| DATA-1 | Layers 2 and 3: `EXTRACTOR_VERSION`, `reextract`, front-matter cache (in the Actions cache, decision 4) | P1 | done |
| AFF-Q | Affiliation quality section in `stats` | P2 | done |
| TEST-4 | Negative tests for the heuristics (the venue cases wait for META-4, as strict `xfail`) | P2 | done |
| TEST-5 | Golden fixture expectations | P2 | done |
| AFF-7, AFF-8 | Superscripts inside words and glued line breaks; leading numbers of names (from the backlog, with TEST-4) | P2 | done |
| DOC-1 | Symptom-first operations runbook (`docs/operations.md`, its signals checked by a test) | P2 | done |
| REL-3 | License and data terms (MIT for the code; the Semantic Scholar terms are read before going public) | P2 | done |

*Exit criteria:* a simulated arXiv outage, layout change, Semantic Scholar 403 and rebase
conflict each end in a clear red run or a summary warning, and nothing is lost.

*Result (2026-10-03, `v0.3.0`).* The four failures run end to end in the tests
(`tests/unit/test_exit_criteria.py`, and `test_commit_data.py` for the rebase conflict):
each ends with exit code 1 and an error annotation naming the cause, the data fetched
validates and is committed, and what was not fetched stays pending for the next run. Three
gaps were found and fixed on the way: a failing command did not say why on the run's page,
a layout change would have pinned error pages in the page cache, and a CLI test wrote into
the repository's cache. `validate`: 26,326 papers in 41 files, 0 errors, 0 warnings. `make
stats` on the day files (2026-09-01 to 2026-10-02, 4,255 papers): affiliations for 78% of
the 4,050 tried, 205 pending; of the affiliated papers, 88% mapped and 87% with a named
institution. `stats --affiliations` (8,499 strings in 3,167 papers): no names of authors,
no string today's cleaning would change, no "is with" sentence, no last author holding
all; left for later, 88 glued strings (plain-text markers, AFF-23), 12 cut off, 196
units without their institution (AFF-10) and 48 addresses alone. The first scheduled run
with the deadline, the breakers, the summary and the page cache (2026-10-02) was green in
55 minutes: 215 new papers, 201 pages read.

## Phase 2: search precision and the daily workflow (1–2 weeks)

| ID | Item | Priority | Status |
|---|---|---|---|
| SRCH-1 | Exact clicked filters, word-prefix typed filters | P1 | done |
| SRCH-2 | Phrase and exclusion scope and tokenization | P2 | done |
| SRCH-3 | Prefix and fuzzy tuning | P1 | done |
| SRCH-4 | Browser history | P1 | done |
| SRCH-5 | Archive permalinks | P1 | done |
| SRCH-17 | Acronym affiliation filters | P2 | done |
| TEST-16 | Relevance tests on real cases | P2 | done |
| SRCH-7, SRCH-12 | A pasted arXiv id finds its paper; stop words alone keep every paper (from the backlog, with TEST-16) | P2, P3 | done |
| PROD-2 | Keyboard triage, seen, since last visit (a banner, not the default period: see the commit) | P1 | done |
| PROD-3 | Saved searches and a watchlist | P2 | done |
| PROD-4 | Reading-list import and safety | P2 | done |
| PROD-5 | BibTeX escaping and keys | P2 | done |
| UX-4 | Focus hidden by the sticky search block | P1 | done |
| UX-1 | Contrast (with TEST-9's check of the two dark palettes) | P2 | done |
| UX-3, UX-5 to UX-12 | Accessibility batch (CSS and ARIA) | P2 | done |
| PROD-6 to PROD-10 | Name the category, about the data, citation transparency, result export, recent-count noise | P2 | done |
| TEST-7 | Web coverage | P2 | done |
| TEST-8 | Smoke test of the built site | P2 | done |

*Exit criteria:* the clicked-filter probes ("Hao Li", "Intel") return exact sets, `"zero shot"`
finds the zero-shot papers, Back works, and the smoke test is green in CI.

*Result (2026-10-03, `v0.4.0`).* Over the days of 1 September to 2 October (4,255 papers),
a clicked "Hao Li" keeps 5 papers and "Intel" 4, the same as an independent recount of the
files (typed, as word prefixes: 43 and 413); `"zero shot"` finds 262 papers (1 at the
audit), `"self supervised"` 146, `"Carnegie Mellon University"` 47 (0). Back returns to
the previous view, typing adds no history entry. In CI, the web job enforces the coverage
of the pure modules (98.7% of lines) and runs the smoke test of the built site in Chromium
(4 checks, green). Deviations from the audit: "since last visit" is a banner, not the
default period (a default that depends on the browser would rewrite shared URLs); the About
page has no live coverage figures (PROD-7); of TEST-9, only the check of the dark palettes.
`validate`: 26,326 papers in 41 files, 0 errors, 0 warnings.

## Phase 3: scale and richer metadata (2–4 weeks, gated by decisions)

| ID | Item | Priority | Status |
|---|---|---|---|
| PERF-1 | Bounded periods, async index build (periods bounded to 10,000 papers, index built in chunks, loaded files kept and requests cancelled; the per-month search shards move to Phase 4, wanted once months of day files outgrow a period) | P1 | done |
| META-1 | Spike, then DOI, published venue and author ids from the weekly Semantic Scholar batch (a separate weekly step, `scholar`, of 52 requests rather than fields added to the 415 of counts) | P1 | done |
| AFF-14 | Keep ROR ids (stored and linked; nodes are still keyed by name, which AFF-13 changes) | P2 | done |
| AFF-3 | OpenAlex retry policy (option A, decision 5: archived papers without affiliations asked again every 30 days while under two years old; no spike, since a retry costs a request) | P1 | done |
| PROD-1 | Fill the 11-month gap | P1 | dropped: no fill, the store grows from September 2026 (decision 1), and no line names the gap |
| ARCH-1 | Retention, size guard and hosting trigger (guards in *Deploy site* and the weekly canary, the trigger in the runbook; pruning on since 2026-10-06, decision 2) | P2 | done |
| PERF-2 | Graph defaults with the author layer (authors of one paper hidden when the layer turns on, the layout in a Web Worker, settled at once under reduced motion, the time-lapse by week or month; PERF-3's clique cap waits for decision 15) | P2 | done |
| PERF-3 | Clique cap for consortium papers (no author-author links above 50 authors, said in the legend: 397,000 links to 112,000 for the 2024 projection) | P2 | done |
| UX-2 | Graph touch zoom and keyboard path (pinch, zoom buttons, matches listed and gone through with Enter, details focused, a label that counts and points to Rankings; decision 14) | P2 | done |
| META-2 | Weekly refresh from the catalog: comments, journal references and their venues, in the archive step; withdrawn papers marked, out of Highly cited and badged (decision 18), with guards against "withdrawn from the workshop", "from the proceedings" | P2 | done |
| META-3 | Provenance of affiliations (`html`, `api`, `openalex`) and institutions (`ror`, `openalex`), with the day read; inferred once for older records, the unmapped unversioned ones left unknown (no `version` or `enriched_from_version`: `extractor` is the version) | P2 | done |
| META-4 | The venue table, and venue detection without mentions | P2 | done |
| PERF-11 | Lazy index build | P2 | done |
| PERF-12 | Split citation counts (at build time: the store keeps one `citations.json`) | P2 | done |
| AFF-23 | Numbered markers glued to the next affiliation start one, in the extraction and in the cleaning (`reclean`); markers mixing a number and symbols read as the number (from the backlog, extraction version 3) | P2 | done |
| AFF-10 | A unit without its institution takes the next line, an author's contact nodes read as one text; with it, thanks notes read across the line wraps of their source, which cut strings ("School of Mechanical and") (from the backlog, extraction version 3) | P2 | done |

*Exit criteria:* a year of day files loads without freezing a phone, and venue coverage of the
archive rises above 52%. The second is met: 89% after the first weekly `scholar` step
(2026-10-04). The first holds by construction: a period loads at most 10,000 papers whatever
is stored, and indexes them in chunks (PERF-1); a phone gets to try it on a year of day files
in September 2027.

*Result (2026-10-06, `v0.5.0`).* The archive's venue coverage is 89% (52% at the audit). A
period loads at most 10,000 papers; turning the graph's authors on blocks the page about
60 ms instead of seconds (PERF-2), and the 2024 archive's author projection has 111,855
links instead of 397,464 (PERF-3). `validate`: 26,552 papers in 43 files, 0 errors, 1
warning (2609.36407 names two authors in one block, "A & B": only the last is placed, a rule
for extraction version 4). `make stats` on the day files (2026-09-01 to 2026-10-05, 4,383
papers): affiliations for 78% of the 4,175 tried, 208 pending; of the affiliated papers, 90%
mapped and 88% with a named institution. `stats --affiliations` (8,691 strings in 3,268
papers), after extraction version 3 and the pages of the flagged papers read again: 2 glued
strings (88 at the end of Phase 1), 6 cut off (12), 19 units without their institution
(196), 11 places alone (48). Every stored affiliation has a provenance: 4,174 day-file papers
from their page and 1 from the arXiv API, 22,168 archived ones from OpenAlex. 12 stored papers
are withdrawn, 5 in day files and 7 in the archive, which its next run drops. Deviations from
the audit: no 11-month fill (PROD-1, decision 1); the per-month search shards move to Phase 4;
META-3 keeps no page version beside `extractor`. Pruning is on (decision 2). Decisions 11,
12, 13 and 17 are still open; the first three gate Phase 4 items.

*META-1 spike (2026-10-03).* One keyed batch of 500 archive papers (a uniform sample) and one
of 500 recent day-file papers, asking `paper/batch` for `externalIds`, `venue`,
`publicationVenue`, `publicationDate`, `journal` and `authors` beside `citationCount`. Each
was refused once (429), then answered in 3.1 s (502 KB) and 1.4 s (278 KB): about 1 KB a
paper, so a sidecar of the 26,000 stored papers needs the same split as the citation counts.
All 1,000 papers are known. Archive: a venue other than arXiv for 91% (the regex finds 52%,
both together 92%), a `publicationVenue` for 84%, a published DOI for 69%, a DBLP id for 99%,
an `authorId` for every author of 93%, the same number of authors as ours for 97%. Recent
papers: a venue for 5% (the regex 19%), so the regex stays first for them. S2 venues are
full names without the year ("Computer Vision and Pattern Recognition", "2018 IEEE/CVF
Conference on …"), and can be wrong: two "ICIP 2026" papers are "International Conference on
Information Photonics". The venue table (META-4) comes first, and the regex wins where both
exist.

## Phase 4: differentiating features and long-term architecture (ongoing)

| ID | Item | Priority | Status |
|---|---|---|---|
| §17.1 | The audit's features worth building, item by item below; #1 to #3 were done in Phase 2 (PROD-2, PROD-3, PROD-5 and PROD-9), #4 to #9 on 2026-10-07 but PROD-11, which waits for a decision, and #10 waits for a year of days | — | in progress |
| PROD-12 | "With code" (§17.1 #4): papers whose abstract or comments link a repository on GitHub or GitLab, else models or data on Hugging Face (918 of 4,832, as the audit's 19%), and a Code link on their card | P2 | done |
| SRCH-11 | Link-outs (§17.1 #5): an unfolded card links the paper on Semantic Scholar, Connected Papers and alphaXiv, each address opened by hand; Hugging Face left out, its page being a 404 for 11 of 12 recent papers | P2 | done |
| §17.1 #6 | Atom feeds, built with the site (the link of an institution of the archive alone, a 404, left out since): one for every institution of the day files and each major venue, their papers of the last 60 days, linked under the filters when the list is filtered on one (2,864 feeds, 20 MB) | — | done |
| CIT-9 | Rising papers (§17.1 #7): each weekly refresh of the counts writes what each paper gained since the one before (`citation-gains.json`, from counts at least 6 days old); cards say "+12 this week", and the Papers and Highly cited views sort by it (Rising). The first gains come with the archive of 2026-10-11, the one of 2026-10-04 having reused the counts of 2026-09-30 | P3 | done |
| PROD-11 | The most cited papers of the last 12 months (§17.1 #7): the store holds none of them from 2025-10-04 to 2026-09-01 (the archive starts at 12 months, and decision 1 left the gap), so it waits for a decision or for the day files to fill a year | P2 | todo |
| §17.1 #8 | Graph: a connection's shared papers in the details, "Focus on this" (the graph of a node's papers alone, `?focus=`, matched as nodes are keyed, and saying when it has no paper among those shown), PNG and GraphML export | — | done |
| SRCH-15 | Venue families (§17.1 #9): "CVPR, any year" (`venue=CVPR*`) before the editions of a venue loaded in more than one, its workshops a family of their own; a venue's view is its filter's link | P3 | done |
| §17.1 #10 | Per-entity timelines in Rankings, once 12 months of data exist | — | todo |
| AFF-13, ARCH-3 | Institution canonicalization in the pipeline (decision 12): the site's rules ported to `institutions.py` (the same name for all 37,789 stored affiliations), ROR first then the rules, registry names made canonical, the archive's too; `make institutions-again`; the site displays only, keeping its acronyms for search | P2 | done |
| AFF-H | Author identity (decision 13): Semantic Scholar's author ids, each kept only where its name is the arXiv author's, merged into the site's records; authors stay keyed by name, since Semantic Scholar has several profiles for most prolific authors (Luc Van Gool three), and a name whose profiles share no institution or co-author says it is perhaps several people (2026-10-07) | P2 | done |
| PROD-17 | Highly cited over several years (asked on 2026-10-07, not in the audit): a range of years or all of them (`?year=2019-2021`, `?year=all`), in the graph and Rankings too; past 10,000 papers (all years hold 22,000, 300 MB once indexed), the best ranked by citations per year of age, saying how many are left out; the graph's list exits keep the archive years; a range beyond the archive is kept to its years, a paper without a count ranks last and a year whose counts fail is said, each citation shard is loaded once | P2 | done |
| UX-24 | Links inside text underlined everywhere, not told by colour alone (WCAG 1.4.1): the footer, About, a card's "Report an error", notices, the feed line and the graph's details (not in the audit) | P2 | done |
| UX-25 | Counts with thousands separators and singular nouns through one helper (`countOf`): "10,000 of 10,000", "Show its paper", a calendar day read as "1 paper"; the dates keep the reader's locale, as UX-17 leaves open (not in the audit) | P3 | done |
| SRCH-8 | A clicked author or affiliation highlights itself as a whole, in the author and affiliation lines only: "Hao Li" no longer marks "lightweight", "linear" and "limited" in titles and abstracts; typed, each piece of a word starts one, as the filter reads it ("J.Smith" marks "John Smith") (from the backlog) | P2 | done |
| UX-23 | Marking a paper seen, unsaving it and late citation counts keep the list's paging and the keyboard focus: the results are derived in three memos, the paging starts over only for a new list (`listKey`, `paging.ts`), and the next card takes the focus (from the backlog) | P3 | done |
| TEST-6 | The tests cannot reach the network: the real httpx transport raises `OfflineError` in every test not marked `network`, an error the pipeline neither retries nor skips (from the backlog) | P2 | done |
| META-9 | A day file's paper that OpenAlex looks up in the archive no longer keeps the HTML extraction's version (`extractor`) of its former affiliations, filled or still empty; `Paper` refuses an `extractor` beside affiliations from another source. Latent: no stored record had one, but day files age into the archive (not in the audit) | P2 | done |
| TEST-15 | A test keeps `Paper.to_record()` and the `Paper` interface of `types.ts` in step, field by field (the build-only `doi` and `author_ids` apart, the fields written only when known optional on the site), and the two `SCHEMA_VERSION`s equal (from the backlog) | P2 | done |
| SEC-2, SEC-7 | Imported reading lists cannot put a `javascript:` or `data:` address on a paper: its arXiv and PDF links are made from its id, its HTML link kept on arxiv.org only, and an id that is not one refused; the "See it on arXiv" link of a `?paper=` that is no arXiv id is left out, and opens in a new tab; the pipeline resolves a listing's HTML link against arXiv and keeps it there only; the footer's links to arXiv, Semantic Scholar, ROR and OpenAlex keep opening in the same tab, on purpose (without `target`, `rel` changes nothing) (from the backlog) | P2, P3 | done |
| PERF-16 | Back from a filter or a paper to the same period, or its preset chosen again, no longer downloads and indexes it again ("Loading papers…" over 3,646 papers): the load is keyed on the period's text (`periodKey`), and a new load lets the former index go first (not in the audit) | P2 | done |
| UX-26 | "Hide seen" says what it hides: the count reads "· 12 seen papers hidden", and a list whose papers are all seen says so, with "Show seen papers", instead of "No paper matches" and remedies that do not help (also for a pasted arXiv id); the paper a link opened stays while it is open, seen or not, and folded, it leaves and hands the focus on (not in the audit) | P2 | done |
| DATA-4, DOC-7 | Papers without an HTML rendering (224 of 4,832) are no longer counted as pending forever: `stats` gives them a *no page* column in the days (the archive's null still waits for OpenAlex), and the update report counts them apart ("1 without an HTML page"), so "no pending papers" can be reached (from the backlog) | P2 | done |
| TEST-10 | An error boundary around the app, and around each view (keyed by it, so another view starts afresh, the tabs staying usable): an error while rendering (a record it cannot draw, a bug) shows what failed, Reload and the correction contact, not a blank page; the smoke test serves a paper without authors to see it; it offers to start over, and draws again once the state or the papers change (`resetKeys`: Back, another period or filter) (from the backlog) | P2 | done |
| UX-15 (cards) | A card says its copies to screen readers ("BibTeX copied"), downloads the BibTeX when the clipboard is refused and says so, opens from its "+N" authors and affiliations ("+3 more authors", which a card without abstract could not show), the first name shown taking the focus from the button that goes away, always has More, and its seen toggle keeps one name, "Seen", its state in `aria-pressed`; the day headings and the graph's focus return wait for a screen-reader check (from the backlog) | P3 | done |
| DEBT-5, DOC-5 | The CLI refuses bad arguments with a usage line, not a traceback or a silent skip (`--max-entries 0`, `--max-html -1`, negative minutes, `nan`, `inf`, a crawl delay past an hour, which `time.sleep` cannot take, a `--match` that is not a regex), `-v` goes after the command too (`stats -v`) and adds to the one before, and `stats --changes` without `--page-cache-dir` (or the cache without `--affiliations`) says so. The long commands (update, backfill, reextract, institutions, citations, scholar, archive) log their progress at info without `-v`, `-q` keeping warnings only, as the audit advised: the README's commands no longer run silent for hours. Dropped: the audit's floor on `--crawl-delay` (the default is robots.txt's 15 s, the tests run at 0, and a lower delay is typed on purpose) (from the backlog) | P3, P2 | done |
| DEBT-5 (shared arguments) | `-c` and `--data-dir` declared once for the commands that take them, and one category default (`DEFAULT_CATEGORY` or every stored category, as each command says) | P3 | todo |
| UX-20 | The graph's cap is "Top institutions & authors" (it never capped papers), and the legend says what it leaves out: "top 100 of 5,993 institutions and authors", naming only the kinds drawn (from the backlog) | P2 | done |
| REL-10 | The full-screen graph names its sources: its settings end with the footer's attribution (`Attribution`) and the date of the citation counts, and the GraphML export says them in a `<desc>`; the PNG, an image for slides, carries none | P2 | done |
| DOC-8, DOC-16 | Drift fixed: the `--help` of update, archive and validate says what they do today (abstracts from RSS, then catchup pages, then the API; OpenAlex, gains, `scholar.json`), report and log lines group digits ("1,234 listed", "207,212 records harvested"), the README's diagram has the archive and Semantic Scholar, its first run the 600-page cap, its citations row every stored paper, and an archived paper from a day file keeps its HTML link (CLAUDE.md, `docs/archive.md`). Decision: arXiv's OAI-PMH gets the contact too, like every arXiv request: the archive's harvest is the heaviest traffic to arXiv, which asks crawlers to be reachable; Semantic Scholar and OpenAlex keep the bare User-Agent | P3, P3 | done |
| ARCH-2 (shared rules) | What every enrichment step repeated, in one place: `Paper.with_affiliations` (setting affiliations from a source resets what came with the former ones; five hand-written copies, one of which forgot the extractor, META-9), `ids_where_named`, and the end of update, backfill and reextract (`_name_and_report`); the collect tests read pages on a fixed day | P2 | done |
| ARCH-2 | Enrichment step interface: a `Step` protocol with per-step counts over HTML, ROR and OpenAlex, which differ in budgets, breakers and checkpoints (the shared rules above come first) | P2 | todo |
| DEBT-2 | A view model for the list (`view-model.ts`: archive or days, order, sort choices, toggles, exports, tested over the six views), and its top bar, header, notices, empty states and footer as components: `app.tsx` from 959 to 643 lines; the smoke test opens Rankings and the reading list | P2 | done |
| DEBT-3 | `GraphView` split: its details panel (`GraphDetails`, whose connections fold back by its key on another node, or when the node leaves the graph and comes back) and its legend (`GraphLegend`) as components, a node's connections a pure, tested `nodeConnections`; 763 to 539 lines | P3 | done |
| ARCH-4 | Multi-category, if wanted | P2 | todo |
| PERF-1 (shards) | Per-month search shards built with the site, for searches over more months than a period loads (from Phase 3) | P2 | todo |
| AFF-25 | Extraction version 4, after the daily re-read of 318 papers with version 3 (2026-10-06): names are never joined to an affiliation, anchors made of joined lines, a creator holding several authors' names is not a person, an "A & B" pair shares its block, "and Health Sciences" goes on with its unit, a pair is never placed at a place alone, an address in brackets ends a thanks sentence instead of dropping it (found after the release, not in the audit) | P2 | done |
| DATA-1 (tables) | The page cache kept no table, and lost the affiliations some author blocks lay out in one (2609.06629): it keeps those of the author block, and a page kept before never empties a paper on re-read, but leaves the cache (found after the release) | P1 | done |
| AFF-18 | The countries of the place-join rule (from the backlog, extraction version 5): the countries affiliations write but names of people, a name ending with a country takes a place in the same one, lines ending with a preposition go on, list connectors and dashes at the end, phone numbers, placeholders and LaTeX commands dropped; US states stay out (their codes are words); version 6: a preposition only after a space ("technikum-wien.at"), an address that ends a line ends its affiliation; version 7: mailboxes before their domain, "X is Robotics Lead at Y" | P3 | done |
| AFF-26 | `make extraction-diff`: the papers today's extraction changes on the cached pages, those that would lose words first, to run before each `EXTRACTOR_VERSION` bump (versions 4 to 7 each fixed a loss of the one before; not in the audit) | P2 | done |
| SRCH-19 | Abstracts as plain text (decision 17): text macros give their argument, links their address, math symbols their character, citations go; wherever an abstract is read, and on the stored papers through `make venues` (from the backlog) | P3 | done |

## Backlog triage (2026-10-07)

The 108 audit items no row above names, checked against the code of 2026-10-07 (`b3bfefc`).
Those done since or no longer true are closed here; the rest stay in the audit's §18
backlog, but for the ones waiting for an answer, listed with the recommended option.

| ID | Status | Why |
|---|---|---|
| ARCH-6 | done | Under DEBT-2 and DEBT-3: the view model and the `GraphView` split |
| CI-5 | done | Under CIT-4: the citations step has its timeout, and a rejected key stops it |
| CIT-10 | done | Under SRCH-11: a card links Semantic Scholar for its references and citations |
| DOC-11 | done | Tags since v0.1.0, `CHANGELOG.md`, release notes from it, a versioned User-Agent |
| DOC-15 | done | Under CIT-11: the docstrings say pruning only decides deletions |
| META-7 | done | DOI, venue and author ids come from Semantic Scholar's weekly batch (META-1, decision 13) |
| PERF-6 | done | Under PERF-11: MiniSearch is built on first need, not on a star click |
| PROD-8 | done | Under PROD-6 to PROD-10: Highly cited states its rule and the counts' date |
| TEST-3 | done | Under CIT-1 to CIT-13: each archive case has its test |
| TEST-14 | done | Under DATA-3: `validate` checks the invariants over the whole store, on every push |
| DATA-8 | dropped | `generated_at` is now the site's "Updated" date and the reference for citations per year: an old stamp would make both wrong |
| CI-15 | dropped | The weekly full refresh of the counts feeds the gains (CIT-9), which a partial refresh would break |
| PERF-9 | dropped | Its premise is false: httpx merges its defaults under the assigned headers, so every request is compressed |
| REL-9 | dropped | REL-3 settled it: arXiv's metadata, abstracts included, is CC0 |

Waiting for the maintainer (the recommendation first):

| ID | Question | Recommendation |
|---|---|---|
| CI-13 | How to pay for Actions | Make the repository public (the site and `data/` already are, the code is MIT), after a scan of the history for secrets |
| AFF-12 | Read again the 833 papers stored without affiliations before extraction versions | Let the daily `reextract` take them within its 50-page cap (about 17 weekdays, up to 12 billed minutes a day), exempt from the layout breaker |
| AFF-20 | Affiliations of archived papers from their published version's OpenAlex record | A one-request spike on 50 published DOIs first; the fallback only if half gain institutions |
| AFF-11 | BMVC and IROS pages give no affiliations (91% and 41% empty) | Two fixtures of each, which takes a few page downloads (or the CI page cache), then a rule and a version bump |
| UX-13 | The tabs overflow on phones | An edge fade when they scroll, the active tab scrolled into view |
| UX-21 | The graph's force sliders | Under a closed "Advanced layout" disclosure |
| UX-22 | Graph settings in shared links | Only the layers and thresholds, applied for the visit, never saved |
| META-5 | Archive dates are approximate | Show archived papers by month ("Mar 2021"), skip arXivRaw |
| SRCH-6 | A query language | Uppercase OR only; no field prefixes yet |
| DEBT-6 | The `fetch` command and its export modules | Delete them: the site's exports and `data/` cover it |
| CIT-5 | Counts fetched and thrown away; refreshing low-rate papers less often | Stop fetching what is thrown away; keep the weekly full refresh (gains) |
| PROD-15 | One tagline | "Follow and search the cs.CV papers announced on arXiv every weekday, with their affiliations, citations and the most cited older papers." |
| SEC-8 | `SECURITY.md` | A short one now, pointing to the correction contact; issue templates once public |
| DOC-3, DOC-4, DOC-2 | ADRs, the calibration scripts, the README's purpose | No ADR folder (the Decisions table is the log), a paragraph on why `data/` is in git; the calibration's key tables in `docs/archive.md`, `experiments/` kept local; a shorter README walkthrough |
| UX-18 | Manifest and favicon | Neither; `theme-color` and a print stylesheet only |
| AFF-16, ARCH-5, ARCH-8, DOC-10, PERF-10, REL-11, UX-19 | Parent organizations, a weekend run, shorter field names, a data-format page, precomputed layouts, a removal channel, the edge color | Defer AFF-16, DOC-10 (to 1.0.0) and REL-11 (until a request); fold ARCH-5 into ARCH-4; drop ARCH-8, PERF-10 and UX-19 |
