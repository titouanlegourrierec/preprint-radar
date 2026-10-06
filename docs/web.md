# The web app: how it works

The design of `web/` module by module: search, URLs, triage, periods, the views and the
graph, and what the build derives from `data/`. Read the part you touch before changing
it; the tests pin most of it (`web/tests/`, the smoke test in `web/e2e/`).

## Search (`search.ts`, `highlight.ts`)

- MiniSearch over title, authors, affiliations and their institutions, venue, abstract and
  comments. Only the last word typed matches as a prefix, from 4 letters, so that acronyms
  stay words ("gan" is not "Gandhi", "mit" not "mitigate"); one typo is allowed from 7
  letters. Highlights follow the same rules (`wholeWord`).
- `"phrases"` match whole words and `-exclusions` word starts, over every searched field
  as one `searchKey` text per paper, so punctuation and hyphens do not count. A pasted
  arXiv identifier or link means that paper; stop words alone keep every paper.
- `PaperIndex` builds its full-text index only for a search with words, or in chunks once
  the list shows (`warm`, while the page is idle), so that the list never waits for it;
  the sidebar's saved-search counts wait for it too (`usePapers().searchable`).
- Author and affiliation filters are a `NameFilter`. A name clicked on a card, a Rankings
  row or a graph node matches exactly: an author by `searchKey`, an institution by the
  name `institutionsOf` gives it, the one the graph and Rankings count, so that a row shows
  as many papers as it says. Text typed in the sidebar matches word prefixes
  (`startsWords`), except a known acronym (`acronymOf`, the `ACRONYMS` of
  `institutions.ts`), which means its institution and is a whole word ("HKU" is not
  "HKUST"). In the URL, `by=`/`at=` are clicked names, `author=`/`aff=` typed text, which
  older links keep.
- The list sorts by relevance, newest or citations (`?sort=citations`: the index orders
  them like newest and `byCitations` ranks them).

## URLs and history (`url-state.ts`)

- Every view is a shareable URL. A step of navigation (`isNavigation`: another view,
  paper, period, year, category, or a filter set by a click) adds a history entry that
  Back undoes; typing and sorting replace the current one.
- The tabs are links, including `?paper=`: a paper permalink in the list, the focused
  paper in the graph. `paperLink` sends an archived paper to its year of the Highly cited
  view, since it has no day file. Share copies the link and changes nothing else.

## Periods and loading (`period.ts`, `data.ts`, `hooks/use-papers.ts`)

- A preset (`?range=`) or a custom date range (`?from=&to=`), shown by
  `components/PeriodPicker.tsx`.
- Every paper of a period is downloaded and indexed in the browser, so a period loads its
  latest days within `PAPER_BUDGET` (10,000 papers: a year of cs.CV, 46,000, would take
  20 s to index and about 480 MB, which crashes phones) and says what it leaves out.
  Links to the former "All days" (`?range=all`) open the longest preset.
- `usePapers` cancels the requests of a period left; `data.ts` keeps the files loaded for
  the next periods (as many papers as a period loads), least recently used out first.
- The *Highly cited* view (`?view=cited&year=`) loads one archive year instead of days,
  ranked by citations. The graph and Rankings show an archive year when the URL has a
  `year` (`?view=graph&year=2017`), else the recent days; the tabs carry the year from the
  Highly cited view, and the Papers tab clears it.

## What the build derives from `data/` (`vite.config.ts`, `tooling/`)

`vite.config.ts` serves `../data` at `/data` in development and copies it into `dist/` on
build (without dotfiles and the `.tmp` files an interrupted write leaves), and in both
derives what only the site uses. The pipeline and `validate` never see these.

- **Citation shards** (`tooling/citation-shards.ts`, `src/citations.ts`): `citations.json`
  split by month for the papers of the day files and by year for the archive
  (`<category>/citations/2026-09.json`, `…/2019.json`). `hooks/use-citations.ts` loads the
  shards of the papers shown (the period or archive year, and the reading list): 11 KB
  gzipped for the recent days instead of 125 KB. A paper filed both in a day file and in
  the archive is in both shards.
- **Published versions** (`tooling/scholar.ts`): the day and archive files get `doi`, and
  the published `venue` where the comments name none, from `scholar.json`.
- `noThirdPartyLoads` (`tooling/third-party.ts`) fails the build if the site would load
  anything from another origin: the About page promises that it loads nothing from other
  websites. Links are fine; fonts, scripts, images or `fetch()` from a CDN are not.
- `base: "./"` keeps the site working under `user.github.io/<repo>/`.

## In this browser only

- **Reading list** (`reading-list.ts`, `hooks/use-reading-list.ts`): stored and exported as
  `{version: 1, papers}`, the bare array of older lists still read. Every entry goes
  through `toPaper`, so that a bad one is skipped instead of breaking the page; import
  merges by id; the list follows other tabs through `storage` events and takes the fresher
  record of a loaded day; a refused save is said, not swallowed.
- **Saved searches** (`saved-searches.ts`): the query string of their words and filters,
  so that they run on any period. The sidebar counts each one's papers new since the last
  visit, and opens them; exported and imported with the reading list.
- **Triage** (`triage.ts`, `hooks/use-triage.ts`), never in the URL: papers marked seen,
  per category, pruned to the last 3 months of identifiers, with "Hide seen"; the newest
  day of the previous visit, fixed for the session, for the "new papers since your last
  visit" banner. The list's keys j/k/o/s/x and `/` use `keyboard.ts`'s typing guard, so
  the search box has no autofocus, which would take them, and Escape leaves it.
- **Preferences** (`preferences.ts`): per-browser settings in `localStorage`.

## Exports and corrections

- `export.ts` writes the results shown as CSV, RIS or Markdown, beside `bibtex.ts` (keys
  with a/b/c on collisions, LaTeX escaping, case-protected words): the Export menu of the
  Papers and Highly cited views. They cite the published DOI when known, else arXiv's.
- `components/About.tsx` (`?view=about`): the data sources, the correction contact and the
  privacy note; keep it true when the pipeline or the app changes. Its link and each
  card's "Report an error" open a mail with a short template to fill in (`report.ts`).

## The graph

- `graph.ts` builds the graph (pure, tested) from three layers: papers, institutions,
  authors. With papers on, a paper links to its authors, and each institution to the
  authors the paper places there, else to the paper itself (never to an unplaced author).
  With papers off, it is the co-occurrence projection (nodes linked when they share a
  paper). Default: papers and institutions, without isolated nodes. An institution node
  carries its ROR id when a paper gives it (`rorId`), linked to ror.org; nodes are still
  keyed by name (AFF-13).
- `graph-layout.ts` gives starting positions (each connected component in one piece, on a
  spiral); `graph-renderer.ts` draws on a canvas and handles the pointer (an imperative
  class); `components/GraphView.tsx` and `GraphSettingsPanel.tsx` are the UI. It is full
  screen, without the search bar and sidebar, and shows every node unless the user sets a
  limit.
- The force layout runs off the main thread (PERF-2): `graph-simulation.ts` is d3-force
  without a DOM (tested in Node), `graph-worker.ts` ticks it in a module worker and posts
  positions as a transferred `Float32Array` at most once a frame, numbered by graph so
  that late positions of a former graph are ignored. The page draws the latest ones and
  stays responsive: turning authors on for five days blocks it once, about 60 ms to build
  the graph, where the layout on the main thread froze it for seconds. A dragged node
  follows the pointer at once and is pinned in the worker. Under reduced motion the worker
  runs the layout to rest at once, for a new graph, new forces or Reheat. The canvas says
  `data-layout="moving"` or `"settled"`, which the smoke test waits for.
- Turning authors on hides authors of a single paper (`authorLayer`, "Author ≥ papers" at
  2, with a note): they are most of the nodes. The time-lapse stops at every day, or at
  the last day of each week or month when there are more than 60 (`replaySteps`): an
  archive year has about 340 days.
- Sizes: a month of papers (3,500) with all three layers is about 23,000 nodes and 34,000
  links (10,000 with authors of two papers or more); the projection with authors about
  19,000 nodes and 100,000 links (every co-author pair); papers and institutions (the
  default) about 5,700 nodes and 6,700 links. The renderer batches drawing into a few
  `Path2D` per frame; graphs over 2,000 nodes use `theta` 1.2, no collisions and a faster
  cooling (about 100 ms a tick for 26,000 nodes, in the worker).
- Node sizes ("Size by"): papers (institutions and authors by their number of papers, area
  proportional, `nodeRadius`; papers all alike) or citations (every node by the citations
  of its papers, summed, `GraphNode.citations`, from the citation shards; unknown counts
  add nothing), on a log scale (`citationRadius`), since counts span 0 to 10⁵ and recent
  papers differ by 1, 5 or 30. The always-labelled biggest nodes of each kind follow the
  chosen size.
- Never set `distanceMax` on the many-body force nor raise `theta` much: nodes then pile up
  in rings (seen with 1,200 and 1.8). Small components get extra gravity once the largest
  component is big, else its repulsion keeps them in a ring far around it.
- Rankings (`rankings.ts`, `components/Rankings.tsx`): the institutions or authors of the
  papers shown, by papers or citations, named through `buildGraph` so that they match the
  graph.
