# Changelog

One minor release per phase of [`docs/roadmap.md`](docs/roadmap.md), a patch for a fix in
between. Item IDs (`DATA-2`, `CIT-11`…) refer to the audit of 2026-09-30
([`docs/audit/2026-09-30.md`](docs/audit/2026-09-30.md)).

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
