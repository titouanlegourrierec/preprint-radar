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
| 2 | Prune at 12 months | Land CIT-11 first (selection no longer depends on prune), then prune once 12 months exist, after CIT-3 | CIT-11 | CIT-11 accepted (2026-10-01); a rolling year once 12 months exist, from September 2027 (2026-10-06) |
| 3 | Revised papers (author list changed) | Re-read the HTML, comparing folded names so renames keep their mapping | DATA-2 | Re-read the HTML (2026-10-01) |
| 4 | Where the front-matter cache lives | The Actions cache first, touched daily | DATA-1 (layer 3) | The Actions cache (2026-10-01) |
| 5 | Archive `[]` affiliations | Spike, then retry OpenAlex while young, and say so in the UI | AFF-3 | Retry OpenAlex while young, option A (2026-10-06) |
| 6 | Filter semantics | Exact for clicked names, word prefix for typed text | SRCH-1 | Exact for clicked names, word prefix for typed text (2026-10-03) |
| 7 | Validation strictness | Fail on structural rules, warn on heuristic ones | DATA-3 | Fail on structural rules, warn on heuristic ones (2026-10-01) |
| 8 | License and data terms | MIT for the code; read the Semantic Scholar terms before going public | REL-3 | MIT for the code (2026-10-01); Semantic Scholar's terms checked, its data can be published (2026-10-06) |
| 9 | Visibility, contact and Actions bill | Confirm the private repository with a public site; choose the correction contact | SEC-9 | Correction contact: titouanlegourrierec@kaist.ac.kr (2026-10-01) |
| 10 | Primary persona | The daily cs.CV follower | Phase 2 order | Both, the daily follower and the literature search: Phase 2 goes by priority and dependencies, search first (2026-10-03) |
| 11 | Multi-category | Stay single-category until Phase 3 is done | ARCH-4 | pending |
| 12 | Institution canonicalization | Move the web rules into the pipeline, with ROR ids | AFF-13 | pending |
| 13 | Author identity | A homonym hint now, Semantic Scholar ids after the META-1 spike | AFF-H | pending |
| 14 | Graph accessibility target | Rankings as the text equivalent now, the full path later | UX-2 | The full path, with touch zoom (2026-10-06) |
| 15 | Consortium papers in the author projection | Skip the clique above 50 authors; keep AFF-4's current rule | PERF-3 | Skip the clique above 50 authors (2026-10-06) |
| 16 | Failure signalling | Red runs for data-affecting failures, an issue for scheduled runs | CI-2 | Red runs for data-affecting failures (2026-10-01); no issue for now |
| 17 | Math in abstracts | Strip text macros now, lazy KaTeX only if asked | SRCH-19 | pending |
| 18 | Withdrawn papers | Exclude from Highly cited, badge in the day views | META-2 | pending |
| 19 | Abstracts by default | On for "Latest day" | Phase 2 | Always collapsed, as now (2026-10-03) |
| 20 | Shipping the audit | Commit it as a frozen baseline | — | Done: `docs/audit/2026-09-30.md` |
| 21 | Versioning | Stay on 0.x; tag a minor release at the end of each phase, with a changelog; 1.0.0 once the public data format is documented and stable | — | Adopted: `v0.1.0` tags the audit commit as the baseline |

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
| ARCH-1 | Retention, size guard and hosting trigger (guards in *Deploy site* and the weekly canary, the trigger in the runbook; pruning stays off until decision 2) | P2 | done |
| PERF-2 | Graph defaults with the author layer (authors of one paper hidden when the layer turns on, the layout in a Web Worker, settled at once under reduced motion, the time-lapse by week or month; PERF-3's clique cap waits for decision 15) | P2 | done |
| PERF-3 | Clique cap for consortium papers (no author-author links above 50 authors, said in the legend: 397,000 links to 112,000 for the 2024 projection) | P2 | done |
| UX-2 | Graph touch zoom and keyboard path | P2 | todo |
| META-2 | Weekly refresh from the catalog: comments, journal references and their venues, in the archive step (withdrawals wait for decision 18, and need guards against "withdrawn from the workshop", "from the proceedings") | P2 | done |
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
| §17.1 | Card link-outs, institution and venue feeds, rising papers, graph ego networks and export | — | todo |
| AFF-13, ARCH-3 | Institution canonicalization in the pipeline | P2 | todo |
| AFF-H | Author identity | P2 | todo |
| ARCH-2 | Enrichment step interface | P2 | todo |
| DEBT-2, DEBT-3 | View model for `app.tsx`, `GraphView` split | P2, P3 | todo |
| ARCH-4 | Multi-category, if wanted | P2 | todo |
| PERF-1 (shards) | Per-month search shards built with the site, for searches over more months than a period loads (from Phase 3) | P2 | todo |
