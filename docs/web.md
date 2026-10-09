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
  Schnabel"), typed text as word starts (each piece of a typed word too, `wordStarts`:
  "J.Smith" marks "John Smith", as the filter keeps it), and every affiliation of a
  clicked institution, however it writes it ("IIT Kanpur" for Indian Institute of
  Technology Kanpur, `affiliationNeedles`); "Li" no longer marks "lightweight" in a title.
- Text is compared folded (`text.ts`): `fold` drops accents and case and writes the
  letters with a stroke or a ligature plainly (ß, ł, ø, ı, đ, æ, as the pipeline compares
  names), so that "Nießner" and "Niessner", or "Bartłomiej" and "Bartlomiej", are one
  author in the graph and Rankings (AFF-24), and `searchKey`, which keys names, graph
  nodes and feeds, also collapses punctuation to one space. Python's
  `institutions.search_key` keys the cases of `tests/fixtures/fold-cases.json` the same
  way, which both test suites read; spacing accents, modifier letters and the middle dot
  (ʻ, ˜, ·), and the combining marks outside `\p{Diacritic}`, still differ, which nothing
  compares today.
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
  older links keep. Typed text, like the search words, searches and goes into the URL
  after a pause of 150 ms, while the field shows it at once (`hooks/use-url-state.ts`,
  `isTypedChange`, PERF-4); a name clicked, a checkbox, a venue or a subject applies at
  once, an edited clicked name stays applied until the pause.
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
- The list sorts by relevance, newest, citations or citations gained (`?sort=citations`,
  `?sort=rising`: the index orders them like relevance and `byCitations` or `byGains` ranks
  them). Both sorts are stable, so equal counts keep the best match first with search
  words, the newest first without (CIT-6); Highly cited ranks the same way.
- "With code" (`?code=1`, PROD-12) keeps the papers whose abstract or comments link a
  repository on GitHub or GitLab, else models or data on Hugging Face (`code.ts`), which
  their card links: 918 of 4,832 stored papers, nearly all "Code is available at". A
  project page (`*.github.io`) or a user's page is not code.
- The venue filter (`venues.ts`, `components/VenueSelect.tsx`) takes a venue ("ECCV
  2026"), any venue (`*`), or a family, every edition of one (`CVPR*`, SRCH-15): the venue
  without its year, as the pipeline writes it for its table's venues and Semantic
  Scholar's alike; a workshop's family is its own ("CVPR Workshop"). `venueFacets` lists a
  family when more than one of its editions is loaded, before them.
- The subject filter (SRCH-9) keeps the papers listed under a subject, primary or
  cross-listed (`subjectsOf`): cs.CV's days hold 478 papers in cs.RO, 256 of them primary.
  Like the venues, its choices (`subjectFacets`) count every loaded paper, not the results,
  and show the code (`cs.RO`), while the URL keeps the name.

## The list views (`app.tsx`, `view-model.ts`)

- `App` holds the state and derives the papers shown; what a view shows and offers is
  worked out once by `viewModel` (DEBT-2): whether it loads archive years
  (`showsArchive`), its order and the sort choices it offers, its toggles and exports.
  The sort control offers Most starred (`?sort=stars`, PROD-18) once the papers loaded have
  the stars of their code: `byStars` ranks them by their GitHub stars, a repository other
  papers link too, or a folder of a larger one (`shared`), with the papers without stars;
  before any `code.json`, `sort=stars` is the view's own order. Five orders take two rows
  on a phone (`.segmented` wraps, its labels whole). A card shows the stars after its Code
  link (`codeBadge`: "★ 1,234", "+12 this week", "shared"; "♥ 23" for the Hub's likes),
  with what they are in its tooltip and for screen readers.
  Each link and control of a card has an icon before its name (UX-28,
  `components/icons.tsx`): the site's logo where the link names one (DOI; Code by
  `codeHost`, GitHub, GitLab or Hugging Face, the pipeline's own hosts, which
  `code-cases.json` pins for both), otherwise one drawn here (PDF, HTML, BibTeX, Share,
  Graph, Seen, More). The logos are Simple Icons' (CC0), copied in, in the link's color
  (`currentColor`): a brand's own would vanish in one theme. Every icon is
  `aria-hidden`, so a control's name stays its text.
  "Hide seen" is the Papers view's alone, "Show abstracts" that of Papers and Highly cited
  (PROD-14; the reading list always shows them), and the Export menu that of Papers,
  Highly cited and the reading list (SRCH-16).
  The rendering is in components: `Topbar` (the tabs), `ResultsHeader` (the count, the
  sort control, the toggles, the Export menu and the reading list's tools), `ListNotices`
  (help, news since the last visit, notes, the filters set, the feed), `NoResults` (why a
  list is empty, and its remedies) and `SiteFooter` (the sources, `Attribution`, which the
  graph's settings show too: REL-10).
- `components/ErrorBoundary.tsx` (TEST-10): a view that fails to draw says so, with Reload,
  a link to start over and the correction contact, and leaves the tabs and the sidebar
  usable; it draws again once the state or the papers change (`resetKeys`: Back, another
  period or filter). Around the whole app, a last one catches the rest.
- Printed (`@media print` in `styles.css`, UX-18), a list is its cards in black on white
  whatever the theme, none cut by a page break, each with its arXiv address under the
  title and an abstract shown printed whole, without the top bar, search, sidebar,
  controls, help notes and graph; a folded card keeps its "+N" authors and affiliations,
  which say how many are left out. Only the cards the list has loaded (40 at a time) print.

## URLs and history (`url-state.ts`)

- Every view is a shareable URL. A step of navigation (`isNavigation`: another view,
  paper, period, year, category, or a filter set by a click) adds a history entry that
  Back undoes; typing and sorting replace the current one.
- The tabs are links, including `?paper=`: a paper permalink in the list, the focused
  paper in the graph. `paperLink` sends an archived paper to its year of the Highly cited
  view, since it has no day file, and one of the most cited of the last 12 months that no
  day file holds (announced before the oldest day, since the `since` of `top_recent` in the
  index) to the view's last 12 months (`archiveRangeOf`). Share copies the link and changes nothing else.
- The parameters, all optional (`readState`, `writeState`; a default value is left out of
  the link; an unknown `view`, `sort`, `range`, `year`, `cat`, `xl` or `code` reads as the
  default, while an unknown `subject` or `venue` is kept and matches no paper):

  | Parameter | Holds | Default | Read by |
  | --- | --- | --- | --- |
  | `q` | The search words | none | every list, Rankings, the graph |
  | `cat` | The category | the store's first | every view |
  | `from`, `to` | A period of days (`from` alone: one day) | `range` | the Papers view, the graph and Rankings without `year` |
  | `range` | A preset: `1`, `5`, `20`, `40` days (`all`, from old links, is `40`) | `5` | the same |
  | `sort` | `relevance`, `newest`, `citations`, `rising` | `relevance` | the lists |
  | `view` | `papers`, `cited`, `graph`, `rankings`, `reading-list`, `about` | `papers` | every view |
  | `paper` | An arXiv id: the paper opened (a list) or selected (the graph) | none | the lists, the graph |
  | `year` | Archive years: `2017`, `2019-2021`, `all`; or `last-12-months` (the latest year until the archive keeps them) | the latest year in Highly cited, the recent days elsewhere | Highly cited, the graph, Rankings |
  | `focus` | A graph node id, `institution:mit`: its papers alone | none | the graph (other views drop it) |
  | `by`, `at` | An author or an institution, as clicked: that name only | none | the lists, Rankings |
  | `author`, `aff` | Typed author or affiliation text: word starts (old links' `by` and `at`) | none | the same |
  | `venue` | A venue (`ECCV 2026`), a family (`ECCV*`) or any (`*`) | none | the lists, Rankings, the graph |
  | `subject` | A subject, primary or cross-listed (`Machine Learning (cs.LG)`; the select shows `cs.LG`) | none | the lists, Rankings |
  | `xl` | `0`: cross-lists hidden | shown | the lists, Rankings |
  | `code` | `1`: papers that link their code | all | the lists, Rankings |

## Periods and loading (`period.ts`, `data.ts`, `hooks/use-papers.ts`)

- A preset (`?range=`) or a custom date range (`?from=&to=`), shown by
  `components/PeriodPicker.tsx`.
- Every paper of a period is downloaded and indexed in the browser, so a period loads its
  latest days within `PAPER_BUDGET` (10,000 papers: a year of cs.CV, 46,000, would take
  20 s to index and about 480 MB, which crashes phones) and says what it leaves out.
  Links to the former "All days" (`?range=all`) open the longest preset.
- `index.html` preloads `data/index.json` (`<link rel="preload" as="fetch" crossorigin>`),
  which every view needs before any day file, so it loads with the page rather than after
  the script; `loadIndex` takes that response, since it asks for the same URL with
  `fetch`'s default mode and credentials, which `crossorigin` gives the preload (the smoke
  test checks the single request): keep the two in step (PERF-14).
- `usePapers` cancels the requests of a period left; `data.ts` keeps the files loaded for
  the next periods (as many papers as a period loads), least recently used out first. It
  loads again only for another period (`periodKey`): Back from a filter or a paper to the
  same period, or its preset chosen again, gives a new object for the same days and keeps
  the index (another period is loaded again, from the files kept); a new load lets the
  former index go before the new one is built.
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
- Or the most cited papers of the last 12 months (`year=last-12-months`, PROD-11): 1,000
  papers the weekly archive keeps apart from its years, in `top-recent.json`
  ([archive.md](archive.md)), since none older than the day files is in the store
  otherwise. `ArchiveRange` is a `YearRange` or `LAST_12_MONTHS`; the Years picker offers
  "Last 12 months" next to "All years" (its year selects then blank), and the source
  select of the graph and Rankings lists it first among the highly cited. They show once
  the index has `top_recent` for the category: before, the link shows the latest year
  (`shownYears`). The count says since when ("first published since 5 Oct 2025"), the
  view's note how they are chosen. Their counts are in the year shards, as the archive's
  (`citationShard`: they are announced before the oldest day), and the build merges
  `scholar.json` into the file as into the others (`paperFiles`, `PAPER_FILE_RE`).
- While a view loads, the results header and the graph say how many papers of what, from
  the counts of `index.json`, which has no file sizes (`format.ts`, `loadingLine`):
  "Loading 3,646 papers of 5 days…" for the days `selectDays` keeps, "Loading 3,407
  highly cited papers of 2024…" or "… of 16 years…" for archive years, all of whose
  papers are downloaded before the budget keeps the best ranked, "Loading 1,000 highly cited
  papers of the last 12 months…"; "Loading papers…" until
  the index arrives. A failed load says why, as an alert with a Retry button, in the lists
  and the graph alike (UX-6): Retry loads again what failed, the index or the papers.
  `loadErrorMessage` reads "Failed to fetch" as "the network or the site did not answer".

## What the build derives from `data/` (`vite.config.ts`, `tooling/`)

`vite.config.ts` serves `../data` at `/data` in development and copies it into `dist/` on
build (without dotfiles and the `.tmp` files an interrupted write leaves), and in both
derives what only the site uses. The pipeline and `validate` never see these.

- **Citation shards** (`tooling/citation-shards.ts`, `src/citations.ts`): `citations.json`
  split by month for the papers of the day files and by year for the archive
  (`<category>/citations/2026-09.json`, `…/2019.json`). `hooks/use-citations.ts` loads the
  shards of the papers shown (the period or archive year, and the reading list): 11 KB
  gzipped for the recent days instead of 125 KB, each once for the page (`data.ts`,
  `citationShard`): one that fails shows no counts, says why in the console and is asked
  for again the next time a view needs it (SRCH-10). A paper filed both in a day file and in
  the archive is in both shards. Each shard carries its papers' gains from
  `citation-gains.json` and the days they span (`gains`), which a card shows ("+12 this
  week", `gainLabel`) and the Rising order sorts by (`?sort=rising`, `byGains`: the most
  gained first, then the most cited), in the Papers and Highly cited views (CIT-9). The
  Rising control shows once a gains file exists; before, `sort=rising` is Most cited.
- **Published versions** (`tooling/scholar.ts`): the day and archive files get `doi`, and
  the published `venue` where the comments name none, from `scholar.json`.
- **Stars of the code** (`tooling/code.ts`, PROD-18): each paper gets `code` from
  `code.json` (`stars`, `gained` the last week, or `likes` on the Hub, and `shared`), only
  where the record's link is still the one its card shows (`codeUrl`: a new version that
  links other code waits for the next weekly refresh). `withSiteFields` merges both files
  in one pass, in development as in the build.
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
  arXiv and PDF links are made from its arXiv id, its HTML link kept only on arxiv.org
  (SEC-2); import
  merges by id; the list follows other tabs through `storage` events and takes the fresher
  record of a loaded day; a refused save is said, not swallowed.
- **Saved searches** (`saved-searches.ts`): the query string of their words and filters,
  so that they run on any period. The sidebar counts each one's papers new since the last
  visit, and opens them; exported and imported with the reading list.
- **The list** (`components/PaperList.tsx`, `paging.ts`) adds 40 cards at a time as its
  end comes into view, and starts over at 40 only for a new list (`listKey`: other words,
  filters, sort, view, period, years or category). A card marked seen while seen papers
  are hidden, or unsaved from the reading list (with x and s, or the card's own buttons),
  leaves without collapsing the list, and the card now at its place takes the focus; the
  paper a link opened (`?paper=`) stays while it is open, seen or not, and leaves once
  folded, handing the focus on the same way. A card's "+N" opens it, its first name
  shown taking the focus from the button, which goes away; a
  list grows only while cards are left, so that one opens at 40 cards, not 80; late
  citation counts re-rank it only when the order uses them (UX-23).
- **Triage** (`triage.ts`, `hooks/use-triage.ts`), never in the URL: papers marked seen,
  per category, pruned to the last 3 months of identifiers, with "Hide seen", whose
  count the header gives ("· 12 seen papers hidden") and which an empty list names as its
  reason, with "Show seen papers" (UX-26); the newest
  day of the previous visit, fixed for the session, for the "new papers since your last
  visit" banner. The list's keys j/k/o/s/x and `/` use `keyboard.ts`'s typing guard, so
  the search box has no autofocus, which would take them, and Escape leaves it.
- **Preferences** (`preferences.ts`): per-browser settings in `localStorage`. The theme
  (`hooks/use-theme.ts`) also colors the browser's bar: `index.html`'s `theme-color` metas
  give each scheme its `--bg`, and a forced theme gives both its own (`theme-color.ts`, and
  the inline script before first paint), which `tests/styles.test.ts` checks (UX-18).

## Withdrawn papers, and old ones announced lately

A paper whose comments say its authors (or arXiv) withdrew it carries `withdrawn`: its
card shows a Withdrawn badge, the reason being in its comments, and the pipeline keeps it
out of Highly cited (decision 18). Reading lists keep the flag.

A paper announced 12 months or more after the month of its identifier, an old paper
cross-listed lately, says "first version 2019" beside its day (`firstVersionYear` in
`format.ts`, PROD-14); an old-style identifier ("cs/0601001") is not read.

## Exports and corrections

- `export.ts` writes the results shown as CSV, RIS or Markdown, beside `bibtex.ts` (keys
  with a/b/c on collisions, LaTeX escaping, case-protected words): the Export menu of the
  Papers, Highly cited and reading list views (`papers.bib`, `reading-list.bib`…). They
  cite the published DOI when known, else arXiv's; like the other views, the reading list
  exports the papers its search and filters show. Beside it, the reading list's Import
  and Export JSON carry the whole list and its saved searches, to another browser.
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
  A name a paper lists twice is one author, placed wherever either occurrence is (AFF-21).
  With papers off, it is the co-occurrence projection (nodes linked when they share a
  paper), except that a paper of more than 50 authors (`MAX_CLIQUE_AUTHORS`) does not link
  its authors to one another, only to its institutions, as the legend says (PERF-3,
  decision 15): the 2024 archive's author projection went from 397,000 links, 39% of them
  from one paper of 561 authors, to 112,000. Default: papers and institutions, without
  isolated nodes. An institution node
  carries its ROR id when a paper gives it (`rorId`), linked to ror.org; nodes are keyed by
  `searchKey` of the name, which the pipeline makes canonical (a company's subsidiaries are
  the company), so that a company stays one node across its ROR entries.
- `components/GraphView.tsx` holds the graph's state (settings, selection, focus, time-lapse)
  and drives the renderer; `GraphDetails` shows the node selected and its connections
  (`nodeConnections`, `linkPapers`), `GraphLegend` what is drawn, `GraphSettingsPanel` the
  settings (DEBT-3). The settings' note under the search gives the share of the papers
  shown whose affiliations are known, with the caveat below half, as Rankings does
  (`affiliationCoverage`, PROD-16).
- `graph-layout.ts` gives starting positions (each connected component in one piece, on a
  spiral); `graph-renderer.ts` draws on a canvas and handles the pointer (an imperative
  class); `components/GraphView.tsx` and the components above are the UI. It is full
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
- "Top institutions & authors" (`maxNodes`) keeps the most frequent institutions and authors,
  never papers, and the legend says how many it leaves out (`Graph.eligible`, UX-20),
  naming only the kinds drawn ("top 100 of 750 institutions" without authors).
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
  graph. Institutions rank on the papers with known affiliations, a minority in the
  youngest archive years (16% of 2025): the note gives their share
  (`format.affiliationCoverage`, "Affiliations known for 331 of 2,018 papers (16%)") and,
  below half, that the others count for no institution (PROD-16).
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
