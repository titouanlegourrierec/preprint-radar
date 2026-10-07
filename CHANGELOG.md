# Changelog

One minor release per phase of [`docs/roadmap.md`](docs/roadmap.md), and one per set of
features in Phase 4, which has no end; a patch for a fix in between. Item IDs (`DATA-2`, `CIT-11`…) refer to the audit of 2026-09-30
([`docs/audit/2026-09-30.md`](docs/audit/2026-09-30.md)).

## Unreleased

### Search

- "With code" keeps the papers that link their code, about one in five: a repository on
  GitHub or GitLab, else models or data on Hugging Face, which their card links (PROD-12).
- An unfolded card links the paper on Semantic Scholar, Connected Papers and alphaXiv,
  which find its related work (SRCH-11).
- A clicked author or affiliation is marked as a whole name, in the author and affiliation
  lines only: filtering on "Hao Li" no longer marks "lightweight" and "linear" in titles
  and abstracts (SRCH-8).
- The venue filter has every edition of a venue at once, "CVPR, any year", its workshops
  apart (SRCH-15).

### Fixes

- Back to a period, or its preset chosen again, no longer loads and indexes its papers
  again: the list stays as it was (PERF-16).

### Triage

- Marking a paper seen (x) while seen papers are hidden, or unsaving it (s) from the
  reading list, keeps the papers loaded below it and gives the focus to the next one; it
  used to fold the list back to 40 papers and lose the keyboard's place. Late citation
  counts no longer fold it either (UX-23).

### Highly cited

- Highly cited shows a range of years, or all of them, not only one: "2019 to 2021",
  "All years", in the graph and Rankings too. Past 10,000 papers (all years hold 22,000),
  the best ranked for their age are shown, and the page says how many are left out
  (PROD-17). From a graph of archive years, "Show all" and opening a paper go to Highly
  cited over the same years, no longer to an empty list of recent days.

### Data

- A paper of the day files looked up by OpenAlex in the archive no longer keeps the
  version of the HTML extraction that gave its former affiliations (META-9).

### Security

- An imported reading list can no longer put a `javascript:` address on a paper's links:
  they are made from its arXiv id, as the store makes them (SEC-2, SEC-7).

### Accessibility

- Links inside text are underlined everywhere (the footer, About, "Report an error",
  notices, the feed line, the graph's details), not told from the text by their colour
  alone (UX-24).
- Counts read right: "10,000 of 10,000 papers" with the reader's separator, and "1 paper"
  rather than "1 papers", in the list, the graph, the calendar and the filters (UX-25).

### Feeds

- Every institution of the recent papers, and each major venue, has an Atom feed of its
  papers of the last 60 days: filtered on one, the list links it, for a feed reader
  (§17.1 #6).

### Graph

- Each connection of a node lists the papers they share ("what did MIT and Google write
  together"), "Focus on this" shows the graph of a node's papers alone, with a link to
  share it, and the graph saves as PNG or GraphML for Gephi (§17.1 #8).

### Citations

- Rising papers: each card says what it gained in the last week ("+12 this week"), and
  the Papers and Highly cited views sort by it (Rising), from the weekly counts of
  2026-10-11 on (CIT-9).

## 0.6.0 (2026-10-07): institutions and authors named by the pipeline

The first release of Phase 4, which goes on without a fixed end: decisions 12, 13 and 17.

### Institutions

- The pipeline names every institution, the site only shows them: ROR's name, a company
  for its subsidiaries, and the rules the site used to apply itself where ROR has none
  (acronyms, companies, the main part of an address). Exports and the data files now carry
  them: the affiliations without an institution went from 2,785 to 122 (AFF-13,
  decision 12).

### Authors

- A name that seems to be several people says so, in the graph and in Rankings ("2
  people?"): Semantic Scholar's profiles of it fall into groups whose papers share no
  institution and no co-author. Its ids do not split authors, as it has several profiles
  for most prolific ones, and they are now checked against the paper's author names
  (AFF-H, decision 13).

### Search

- Abstracts read as text: "\textbf{GestureFAR}" is "GestureFAR", "\url{...}" its address,
  "$\sim$18--20\%" is "~18–20%", and citations go; the search no longer matches "textbf"
  for "text" (SRCH-19, decision 17).

### Fixes

- Affiliations read better (extraction version 7): a sentence that ends with its authors'
  mailboxes ("{a, b}@tum.de") is no longer dropped, which gave 2610.03283 back its
  Technical University of Munich, and "X is Robotics Lead at Y" gives Y, without the
  person (AFF-18).

## 0.5.1 (2026-10-06): affiliations read again

A patch after Phase 3: what the daily re-read of the stored papers with extraction version 3
showed.

### Fixes

- Affiliations read better (extraction version 4). Version 3 put author names inside an
  affiliation when they were printed just before it ("Terrence Chen, Ziyan Wu, United
  Imaging Intelligence"), and gave every affiliation to the last author of a paper whose
  authors are all in one block: the markers place them again. Two authors written as a
  pair ("A & B") share their block, "Faculty of Medicine" / "and Health Sciences" is one
  affiliation, and a thanks note ending with an address in brackets is no longer dropped
  (AFF-25).
- More places join their affiliation (extraction version 5): countries from Kazakhstan to
  Sri Lanka are known, "National Research Council Canada" takes "London, ON, Canada", a
  line ending with "of" goes on with the next, and phone numbers, "TODO" placeholders and
  LaTeX commands printed as text are dropped (AFF-18). Version 6 keeps the domain of an
  address ("technikum-wien.at") from reading as "at", and an affiliation followed by an
  address on its line is kept, without it.
- The page cache keeps the tables of author blocks, where some papers lay out their
  affiliations: read again from the cache, 2609.06629 had lost its five. A page kept before
  never empties a paper's affiliations; it is downloaded again (DATA-1).

### Development

- The tests hide `FORCE_COLOR`, which some terminals export and which styled the plain
  lines they assert on.

## 0.5.0 (2026-10-06): longer periods and richer metadata

Phase 3 of the roadmap.

### Longer periods

- A period loads its latest days within 10,000 papers and says what it leaves out; links
  to the former "All days" open the longest period (PERF-1).
- The search index is built when a search needs it, or in chunks while the page is idle,
  so that the list never waits for it; loaded files are kept for the next periods, and
  the requests of a period left are cancelled (PERF-1, PERF-11).
- Citation counts load for the papers shown only: 11 KB gzipped instead of 125 KB for the
  recent days (PERF-12).
- The graph lays itself out in the background, so that the page stays responsive: turning
  authors on no longer freezes it for seconds, and hides authors of a single paper (most
  of the nodes), which "Author ≥ papers" brings back. The time-lapse of an archive year
  goes week by week, and with reduced motion the layout appears settled at once (PERF-2).
- The graph zooms with two fingers and with +, − and Fit buttons; its Highlight field lists
  the first matches, and Enter goes through all of them, "3 of 500 matches" (UX-2).
- Without papers, the authors of a paper of more than 50 authors are no longer all linked
  to one another, which said nothing of who works with whom: the 2024 archive's author
  graph has 112,000 links instead of 397,000 (PERF-3).

### Richer metadata

- Venues come from a table of venues and their full names, never from a mere mention
  ("compared with CVPR 2025", "rejected from", "ranked first at the challenge"); years of
  page ranges no longer count, glued and short years do ("CVPR16", "BMVC2026") (META-4).
- The published version, from Semantic Scholar every week: its DOI, linked on cards and
  cited by the BibTeX, RIS and CSV exports, and its venue where the comments name none.
  The archive's papers with a venue go from 52% to 89% (META-1).
- Institutions keep their ROR id, linked from the graph's institution nodes (AFF-14).
- Archived papers of the last two years that OpenAlex knew no affiliations for are asked
  for again every month: OpenAlex learns recent papers over months, and only 16% of 2025's
  archived papers had affiliations (AFF-3).
- Each paper says where its affiliations came from (its HTML page, the arXiv API or
  OpenAlex) and who named its institutions, and when (META-3).
- Papers their authors withdrew from arXiv are marked Withdrawn, and left out of Highly
  cited, however cited (decision 18).
- Every week, stored papers take the comments and journal reference of their latest
  version, and the venue they give: a paper "under review" when announced shows where it
  was accepted (META-2).
- Affiliations read better (extraction version 3): IEEE thanks notes no longer lose the
  end of a sentence their source wrapped ("School of Mechanical and"); numbered
  affiliations written on one line are told apart and their authors placed ("Cornell
  University 2University of California, Berkeley"); a department takes the institution
  written on the next line (AFF-23, AFF-10). On 48 sample pages, 244 authors placed
  instead of 154; in the stored papers, read again where a sign pointed at them, strings
  holding two affiliations went from 89 to 2, and departments without their institution
  from 206 to 19.

### Fixes

- j and k reach the list as soon as the page loads (the search box no longer takes the
  focus), and Share only copies the link.
- "Report an error" opens a mail with a short template to fill in.

### Operations

- The data workflows are dispatched on time by an outside scheduler; GitHub's own
  schedules, which started runs hours late, are fallbacks that stop once the day's run
  succeeded.
- *Deploy site* warns above 600 MB of site and fails above 800 MB; the weekly canary warns
  above 500 MB of repository (ARCH-1).
- The weekly archive keeps a rolling year of day files: those older than 12 months leave
  the site, their cited papers staying in the archive; nothing goes before September 2027
  (decision 2).

## 0.4.0 (2026-10-03): precise search and a daily routine

Phase 2 of the roadmap.

### Search

- A name clicked on a card, a Rankings row or a graph node filters exactly that author or
  institution, which the graph and Rankings count alike; text typed in the sidebar matches
  word prefixes, and a known acronym ("NUS", "HKU") its institution (SRCH-1, SRCH-17,
  decision 6).
- Phrases and exclusions cover every searched field, authors and affiliations included,
  on whole words: `"zero shot"` finds "zero-shot", `-google` leaves out Google's papers
  (SRCH-2).
- Only the last word typed matches as a prefix, and a typo is allowed from 7 letters:
  "mit" no longer finds "mitigate", nor "gan" "Gandhi"; highlights follow (SRCH-3).
- The Back button returns to the previous view, search or paper; tabs are links (SRCH-4).
- Share links of archived papers open their year (SRCH-5); a pasted arXiv identifier or
  link finds its paper (SRCH-7); stop words alone keep every paper (SRCH-12).

### Daily use

- Triage from the keyboard (j, k, o, s, x, /), papers marked seen and "Hide seen", and
  "N new papers since your last visit" (PROD-2).
- Saved searches, each with its papers new since the last visit (PROD-3).
- The reading list can be imported, follows other tabs, takes fresher records and says
  when the browser refuses to store it; its export carries the saved searches (PROD-4).
- BibTeX that compiles: special characters escaped, case-sensitive words braced, colliding
  keys told apart, the arXiv DOI and the venue (PROD-5).
- "Export N" gives the results as BibTeX, CSV, RIS or Markdown (PROD-9).

### Interface and accessibility

- The sticky search bar no longer hides the focused control (UX-4); text, links and
  fields pass WCAG AA contrast in both themes (UX-1).
- Focus rings, accessible names, page titles, a skip link, empty states, a Retry on load
  errors, active filters as removable chips, a line per view saying what it shows, an
  introduction to the graph (UX-3, UX-5 to UX-12).
- The header names the category; cards offer "Report an error"; the Highly cited view
  explains its choice and dates its counts; counts of 0 are hidden on recent papers, and
  "Most cited" says when nearly all results tie (PROD-6 to PROD-10).

### Development

- Relevance tests on real cases (TEST-16); the coverage of the web's pure modules is
  enforced (TEST-7); a smoke test of the built site runs in Chromium in CI (TEST-8); a test
  keeps the two dark palettes identical.

## 0.3.0 (2026-10-03): a pipeline that heals itself and says what happened

Phase 1 of the roadmap.

### Runs that fail clearly, and lose nothing

- Reading HTML pages stops at a deadline (the run ends green and commits what it read),
  after 5 failed pages in a row (arXiv down: red), or when 90% of at least 40 pages give
  no affiliation (a layout change: red, the papers stay pending and their pages leave the
  cache). SIGTERM saves the progress first (REL-1, REL-2, REL-6).
- A weekly canary runs the network tests against the live arXiv (REL-1).
- Every run writes a summary on its page: each command's report, the validation, the
  freshness of the data and of the citation counts, the coverage and the signs of wrong
  affiliations. Warnings flag stale data and stale counts; a failure that touches data,
  or any command that fails on an error, is a red run with an error annotation saying why
  (CI-2, decision 16).
- The site is deployed only when the run pushed data (CI-3).
- A rejected Semantic Scholar key stops at the first request and fails the run; a busy
  Semantic Scholar is given up after 10 minutes in the daily step (CIT-4).
- The four failures of the exit criteria run end to end in the tests: an arXiv outage, a
  layout change, a rejected key, a rebase conflict on the data commit.

### Data quality

- Stored papers are read again when the extraction improves: the extraction has a
  version (`EXTRACTOR_VERSION`, stored as `extractor`), `reextract` reads older papers
  again, from a cache of front matters kept in the Actions cache, and the daily run does
  it by itself (DATA-1, layers 2 and 3).
- `stats --affiliations` counts the signs of wrong affiliations, with examples, in the
  stored data and in what today's extraction gives for the cached pages (AFF-Q).
- Leading numbers of names are kept ("54th Research Institute", "3M Company", "3D Vision
  Lab"); superscripts inside a word and line breaks, written or lost by LaTeXML, no longer
  split or glue affiliations; links set as authors and markers of affiliation lines no
  longer misplace authors (AFF-7, AFF-8). 29 stored papers were repaired.

### Development

- "Must not produce" tests for the heuristics, and a golden file of everything each HTML
  fixture gives (TEST-4, TEST-5). Every test runs in its own directory.
- `docs/operations.md`: a runbook by symptom, whose quoted signals a test checks against
  the code (DOC-1).
- MIT license for the code (REL-3). Pushing a `v*` tag creates the GitHub release, with
  this file's entry as notes.

## 0.2.0 (2026-10-01): stop publishing wrong data

Phase 0 of the roadmap.

### Data quality

- Author names are no longer stored as affiliations: names are compared without accents,
  punctuation, IEEE grades or "Jr.", list by list, and a source that only names authors
  leaves its turn to the next one (AFF-1).
- Obfuscated e-mail addresses (`(at)`, `[at]`) and lists of mailbox names are stripped
  (AFF-2); link and contribution leftovers, units cut off by a line break and lone countries
  are rejected, in the pipeline and in the web's institution names (AFF-5).
- "A and B are with X" gives X wherever it is written, and places A and B; "X, and also
  with Y" gives both affiliations (AFF-6).
- A new version that changes a paper's author list has its HTML read again, instead of
  keeping a mapping that no longer matches its authors; `Paper` refuses such a mapping, and
  the graph places nobody when one is out of step (DATA-2, AFF-15).
- `reclean` applies the cleaning rules to the stored day files, offline (DATA-1, layer 1).
  Run over September: 284 of 2,889 affiliated papers changed.
- A paper is stored once, on the first day it was announced (DATA-5).

### Pipeline and workflows

- `validate` checks `data/` against its contract: structural rules fail, heuristic ones
  warn. The data workflows run it before committing and push nothing when it fails; CI runs
  it on every push (DATA-3).
- The data commit is replayed on a `main` that moved during the run: conflicts on
  `index.json` and `citations.json` are settled, and a commit that cannot be pushed is kept
  as an artifact (CI-1).
- `update` writes the index as soon as the listing is saved, and both `update` and
  `backfill` write it after a failure (DATA-6). Leftovers of interrupted writes stay out of
  git and of the site (DATA-7).

### Citation archive

- Papers in day files compete for the archive once first seen 12 months ago, whether or not
  old day files are pruned; their first appearance is the earlier of the day file and the
  catalog's date (CIT-11, CIT-3, CIT-12, CIT-13).
- An archived paper whose count is missing one week is ranked on the previous week's
  (CIT-2), and a run below the 95% coverage gate merges its counts instead of replacing
  them (CIT-1).

### Site

- An About view gives the data sources, a contact for corrections and removal, and a
  privacy note; the build fails if the site would load anything from another origin
  (SEC-9, SEC-10).

### Development

- Coverage below 95% fails CI and `make coverage` (TEST-1).

## 0.1.0 (2026-09-30): baseline

The state of the project at the audit of 2026-09-30, tagged as the starting point of the
roadmap.
