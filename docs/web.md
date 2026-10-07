# The web app: how it works

The design of `web/` module by module: search, URLs, triage, periods, the views and the
graph, and what the build derives from `data/`. Read the part you touch before changing
it; the tests pin most of it (`web/tests/`, the smoke test in `web/e2e/`).

## Search (`search.ts`, `highlight.ts`)

- MiniSearch over title, authors, affiliations and their institutions, venue, abstract and
  comments. Only the last word typed matches as a prefix, from 4 letters, so that acronyms
  stay words ("gan" is not "Gandhi", "mit" not "mitigate"); one typo is allowed from 7
  letters. Highlights follow the same rules (`wholeWord`). The names filtered on are
  marked each in its own line only (`nameHighlights`, SRCH-8): a clicked name as a whole,
  across punctuation as the filter compares it ("Julia A. Schnabel" marks "Julia A
  Schnabel"), typed text as word starts, and every affiliation of a clicked institution,
  however it writes it ("IIT Kanpur" for Indian Institute of Technology Kanpur,
  `affiliationNeedles`); "Li" no longer marks "lightweight" in a title.
- `"phrases"` match whole words and `-exclusions` word starts, over every searched field
  as one `searchKey` text per paper, so punctuation and hyphens do not count. A pasted
  arXiv identifier or link means that paper; stop words alone keep every paper.
- `PaperIndex` builds its full-text index only for a search with words, or in chunks once
  the list shows (`warm`, while the page is idle), so that the list never waits for it;
  the sidebar's saved-search counts wait for it too (`usePapers().searchable`).
- Author and affiliation filters are a `NameFilter`. A name clicked on a card, a Rankings
  row or a graph node matches exactly: an author by `searchKey`, an institution by the
  name `institutionsOf` gives it, the one the graph and Rankings count, so that a row shows
  as many papers as it says. The site names no institution itself: `institutionsOf` reads
  the store's `institutions`, which the pipeline names (`src/preprint_radar/institutions.py`,
  AFF-13); a record without them (not named yet, or kept in a browser before) names none. Text typed in the sidebar matches word prefixes
  (`startsWords`), except a known acronym (`acronymOf`, the `ACRONYMS` of
  `institutions.ts`), which means its institution and is a whole word ("HKU" is not
  "HKUST"). In the URL, `by=`/`at=` are clicked names, `author=`/`aff=` typed text, which
  older links keep.
- Authors are keyed by name (AFF-H, decision 13): Semantic Scholar has several profiles
  for most prolific authors (Luc Van Gool three, of 88, 74 and 18 papers; Dacheng Tao five),
  so its ids would split them. The build gives each record its authors' ids
  (`author_ids`, from `scholar.json`), and `graph.countPeople` groups a name's profiles
  that share an institution or a co-author among the papers shown: more than one group of
  at least two papers (`PERSON_PAPERS`: one-paper profiles are often orphan duplicates) is
  probably more than one person, which the details panel and Rankings say ("2 people?",
  `severalPeople`). Their papers stay counted together. Over the whole store, 1,304 names
  get it: Wei Wang 8, Hao Li 5; Luc Van Gool, Dacheng Tao one each, and Kaiming He 2, a
  7-paper profile sharing nothing with the other.
- The list sorts by relevance, newest or citations (`?sort=citations`: the index orders
  them like newest and `byCitations` ranks them).
- "With code" (`?code=1`, PROD-12) keeps the papers whose abstract or comments link a
  repository on GitHub or GitLab, else models or data on Hugging Face (`code.ts`), which
  their card links: 918 of 4,832 stored papers, nearly all "Code is available at". A
  project page (`*.github.io`) or a user's page is not code.
- The venue filter (`venues.ts`, `components/VenueSelect.tsx`) takes a venue ("ECCV
  2026"), any venue (`*`), or a family, every edition of one (`CVPR*`, SRCH-15): the venue
  without its year, as the pipeline writes it for its table's venues and Semantic
  Scholar's alike; a workshop's family is its own ("CVPR Workshop"). `venueFacets` lists a
  family when more than one of its editions is loaded, before them.

## The list views (`app.tsx`, `view-model.ts`)

- `App` holds the state and derives the papers shown; what a view shows and offers is
  worked out once by `viewModel` (DEBT-2): whether it loads archive years
  (`showsArchive`), its order and the sort choices it offers, its toggles and exports.
  The rendering is in components: `Topbar` (the tabs), `ResultsHeader` (the count, the
  sort control, the toggles, the Export menu and the reading list's tools), `ListNotices`
  (help, news since the last visit, notes, the filters set, the feed), `NoResults` (why a
  list is empty, and its remedies) and `SiteFooter`.

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
  the next periods (as many papers as a period loads), least recently used out first. It
  loads again only for another period (`periodKey`): Back to a period, or its preset
  chosen again, gives a new object for the same days and keeps the index; a new load lets
  the former index go before the new one is built.
- The *Highly cited* view (`?view=cited&year=`) loads archive years instead of days,
  ranked by citations: one (`year=2017`), a range (`year=2019-2021`, the From and To
  selects of `components/ArchiveYears.tsx`) or all of them (`year=all`, which stays all
  as years are added); without `year`, the latest. Past `PAPER_BUDGET` papers (all years
  hold 22,000: 100 MB, 300 MB once indexed), it keeps the best ranked by citations per
  year of age, the archive's own score (`archive-years.ts`, `bestRanked`, from the
  citation shards of those years), and says how many it leaves out (PROD-17). The graph
  and Rankings show archive years when the URL has a `year` (`?view=graph&year=all`),
  else the recent days; the tabs carry the years from the Highly cited view, and the
  Papers tab clears them. A graph of archive years lists its papers ("Show all",
  double-click, "Open in the list") in Highly cited over the same years, as Rankings does.

## What the build derives from `data/` (`vite.config.ts`, `tooling/`)

`vite.config.ts` serves `../data` at `/data` in development and copies it into `dist/` on
build (without dotfiles and the `.tmp` files an interrupted write leaves), and in both
derives what only the site uses. The pipeline and `validate` never see these.

- **Citation shards** (`tooling/citation-shards.ts`, `src/citations.ts`): `citations.json`
  split by month for the papers of the day files and by year for the archive
  (`<category>/citations/2026-09.json`, `…/2019.json`). `hooks/use-citations.ts` loads the
  shards of the papers shown (the period or archive year, and the reading list): 11 KB
  gzipped for the recent days instead of 125 KB. A paper filed both in a day file and in
  the archive is in both shards. Each shard carries its papers' gains from
  `citation-gains.json` and the days they span (`gains`), which a card shows ("+12 this
  week", `gainLabel`) and the Rising order sorts by (`?sort=rising`, `byGains`: the most
  gained first, then the most cited), in the Papers and Highly cited views (CIT-9). The
  Rising control shows once a gains file exists; before, `sort=rising` is Most cited.
- **Published versions** (`tooling/scholar.ts`): the day and archive files get `doi`, and
  the published `venue` where the comments name none, from `scholar.json`.
- **Atom feeds** (`tooling/feeds.ts`, `src/feeds.ts`, §17.1 #6): `feeds/<category>/
  institutions/<slug>.xml` for every institution the day files name, and
  `feeds/<category>/venues/<venue>.xml` for each major venue (every edition, not the
  workshops), with their papers of the last 60 days (`FEED_DAYS`), at most 30 and 100. The
  slug is the name's `searchKey`, hyphenated, so that the site finds a feed from the name
  it filters on (`feedOf`: an institution clicked that the loaded days name, since an
  institution of the archive alone has none, else a major venue) and links it under the
  filters; an institution keeps its feed while the store holds one of its papers,
  empty after 60 quiet days. Entries are the site's records (with Semantic Scholar's
  venues), ten authors and "and N more". The deploy workflow passes the site's address
  (`PREPRINT_RADAR_SITE_URL`, from `configure-pages`) for each feed's id and `self` link;
  a local build gives `urn:` ids and no links. About 2,900 feeds, 20 MB for five weeks of
  days; a 60-day window keeps it there as the days grow.
- `noThirdPartyLoads` (`tooling/third-party.ts`) fails the build if the site would load
  anything from another origin: the About page promises that it loads nothing from other
  websites. Links are fine; fonts, scripts, images or `fetch()` from a CDN are not.
- `base: "./"` keeps the site working under `user.github.io/<repo>/`.

## In this browser only

- **Reading list** (`reading-list.ts`, `hooks/use-reading-list.ts`): stored and exported as
  `{version: 1, papers}`, the bare array of older lists still read. Every entry goes
  through `toPaper`, so that a bad one is skipped instead of breaking the page, and its
  links are made from its arXiv id, never taken from the file (SEC-2); import
  merges by id; the list follows other tabs through `storage` events and takes the fresher
  record of a loaded day; a refused save is said, not swallowed.
- **Saved searches** (`saved-searches.ts`): the query string of their words and filters,
  so that they run on any period. The sidebar counts each one's papers new since the last
  visit, and opens them; exported and imported with the reading list.
- **The list** (`components/PaperList.tsx`, `paging.ts`) adds 40 cards at a time as its
  end comes into view, and starts over at 40 only for a new list (`listKey`: other words,
  filters, sort, view, period, years or category). A card marked seen while seen papers
  are hidden, or unsaved from the reading list (with x and s, or the card's own buttons),
  leaves without collapsing the list, and the card now at its place takes the focus; a
  list grows only while cards are left, so that one opens at 40 cards, not 80; late
  citation counts re-rank it only when the order uses them (UX-23).
- **Triage** (`triage.ts`, `hooks/use-triage.ts`), never in the URL: papers marked seen,
  per category, pruned to the last 3 months of identifiers, with "Hide seen", whose
  count the header gives ("· 12 seen papers hidden") and which an empty list names as its
  reason, with "Show seen papers" (UX-26); the newest
  day of the previous visit, fixed for the session, for the "new papers since your last
  visit" banner. The list's keys j/k/o/s/x and `/` use `keyboard.ts`'s typing guard, so
  the search box has no autofocus, which would take them, and Escape leaves it.
- **Preferences** (`preferences.ts`): per-browser settings in `localStorage`.

## Withdrawn papers

A paper whose comments say its authors (or arXiv) withdrew it carries `withdrawn`: its
card shows a Withdrawn badge, the reason being in its comments, and the pipeline keeps it
out of Highly cited (decision 18). Reading lists keep the flag.

## Exports and corrections

- `export.ts` writes the results shown as CSV, RIS or Markdown, beside `bibtex.ts` (keys
  with a/b/c on collisions, LaTeX escaping, case-protected words): the Export menu of the
  Papers and Highly cited views. They cite the published DOI when known, else arXiv's.
- An unfolded card links the paper on Semantic Scholar, Connected Papers and alphaXiv
  (`link-outs.ts`, SRCH-11), which find related work from its arXiv id: a lexical "related
  papers" here would be a weaker copy. Each address was opened by hand; Hugging Face is
  left out, its page being a 404 for most recent papers.
- `components/About.tsx` (`?view=about`): the data sources, the correction contact and the
  privacy note; keep it true when the pipeline or the app changes. Its link and each
  card's "Report an error" open a mail with a short template to fill in (`report.ts`).

## The graph

- `graph.ts` builds the graph (pure, tested) from three layers: papers, institutions,
  authors. With papers on, a paper links to its authors, and each institution to the
  authors the paper places there, else to the paper itself (never to an unplaced author).
  With papers off, it is the co-occurrence projection (nodes linked when they share a
  paper), except that a paper of more than 50 authors (`MAX_CLIQUE_AUTHORS`) does not link
  its authors to one another, only to its institutions, as the legend says (PERF-3,
  decision 15): the 2024 archive's author projection went from 397,000 links, 39% of them
  from one paper of 561 authors, to 112,000. Default: papers and institutions, without
  isolated nodes. An institution node
  carries its ROR id when a paper gives it (`rorId`), linked to ror.org; nodes are keyed by
  `searchKey` of the name, which the pipeline makes canonical (a company's subsidiaries are
  the company), so that a company stays one node across its ROR entries.
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
- Touch and keyboards (UX-2, decision 14): two fingers pinch to zoom (`pinchView`, about
  their midpoint, a second finger turning a drag into a pinch), and +, − and Fit buttons
  sit on the canvas. The Highlight field is a combobox: its first 10 matches are listed
  under it (arrows and Enter choose one, whose details then take the focus), and Enter or
  Shift+Enter go through all the matches, which a status line counts ("3 of 500 matches:
  MIT"). The canvas's label counts its nodes and links, and its description points to
  Rankings, the same institutions and authors as a table.
- Turning authors on hides authors of a single paper (`authorLayer`, "Author ≥ papers" at
  2, with a note): they are most of the nodes. The time-lapse stops at every day, or at
  the last day of each week or month when there are more than 60 (`replaySteps`): an
  archive year has about 340 days.
- Sizes: a month of papers (3,500) with all three layers is about 23,000 nodes and 34,000
  links (10,000 with authors of two papers or more); the projection with authors about
  19,000 nodes and 100,000 links (every co-author pair, up to 50 authors); papers and institutions (the
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
- What two nodes did together, and with whom one works (§17.1 #8): each of a node's
  connections in the details lists the papers their link stands for on a click
  (`linkPapers`: every shared paper when papers are nodes, in the projection only those
  that link them, as many as the link's weight; refolded for another node); "Focus on
  this" shows the graph of the node's papers alone (`papersOfNode`, `?focus=
  institution:<key>`, the node id), its institutions and authors as the settings show
  them, with a bar that says so and goes back to everything. The id matches as nodes are
  keyed (`institution:MIT` is `institution:mit`), a node the graph does not draw is named
  by its usual spelling (`nodeLabel`), and a focus with no paper among those shown
  (another period, year or venue) says so. The focus is the graph's alone: another view
  drops it (`use-url-state.ts`). A node's papers are its papers among those loaded,
  matched as `buildGraph` keys nodes, which is simpler than a neighbourhood in hops once
  papers are nodes too (an institution is two or three hops from another).
- Export (the settings' PNG and GraphML buttons): the canvas as drawn on the page's
  background (`GraphRenderer.toPng`), and the nodes (kind, name, papers, citations, ROR
  id) and links (weight) of the graph shown for Gephi, Cytoscape or NetworkX
  (`graph-export.ts`).
