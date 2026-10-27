# The web app: how it works

The design of `web/` module by module. Read the part you touch before changing it; the tests
pin most of it (`web/tests/`, the smoke test in `web/e2e/`).

## Search (`search.ts`, `highlight.ts`)

- MiniSearch over title, authors, affiliations and their institutions, venue, abstract and
  comments, weighed by `FIELD_BOOSTS` (title 3, authors 2, affiliations and venue 1.5,
  abstract 1, comments 0.5). Only the last word typed is a prefix, from 4 letters, so that
  acronyms stay words ("gan" is not "Gandhi"); one typo is allowed from 7 letters.
  Highlights follow the same rules (`wholeWord`); a filtered name is marked in its own line
  only (`nameHighlights`, `wordStarts`, `affiliationNeedles`, SRCH-8). In a card a mark
  draws itself once, a highlighter's stroke of 320 ms, the title's first (UX-56):
  `Highlighted` keys each by where it starts, so that a word found later strokes alone,
  and nothing moves under reduced motion; high-contrast modes get the system's `Mark`.
- Text is compared folded (`text.ts`): `fold` drops accents and case and spells ß, ł, ø, ı,
  đ, æ plainly, so "Nießner" and "Niessner" are one author (AFF-24); `searchKey`, the key of
  names, graph nodes and feeds, also collapses punctuation. Python's
  `institutions.search_key` must agree: both test suites read
  `tests/fixtures/fold-cases.json`. They still differ on spacing accents, modifier letters,
  the middle dot and combining marks outside `\p{Diacritic}`, which nothing compares.
- `"phrases"` match whole words and `-exclusions` word starts, over one `searchKey` text per
  paper, so punctuation and hyphens do not count. An uppercase `OR` joins the word or phrase
  on each side (SRCH-6: `video nerf OR gan`); a lowercase "or" is a stop word. `parseQuery`
  groups the alternatives (`either`), `queryTree` asks MiniSearch for every free word and
  one alternative per group, `holdsEither` checks a phrase's word order. A pasted arXiv id
  or link means that paper; stop words alone keep every paper. No field prefixes (`title:`).
- Relevance favors papers holding consecutive query words side by side (SRCH-18,
  `adjacentPatterns`, stop words allowed between them): holding every pair triples the score
  (`ADJACENCY_BOOST`), enough to beat the words apart in an abstract, not in a title. It
  took the top 20 results holding the words as typed from 84% to 95%.
- `PaperIndex` builds its full-text index only for a search with words, or in idle chunks
  once the list shows (`warm`), so the list never waits (`usePapers().searchable`).
- Name filters (`NameFilter`): a name clicked on a card, a Rankings row or a graph node
  (`by`, `at`) matches exactly, an author by `searchKey`, an institution by the name
  `institutionsOf` gives it, as the graph and Rankings count, so a row shows as many papers
  as it says. The site names no institution itself: it reads the record's `institutions`
  (`src/preprint_radar/institutions.py`, AFF-13). Typed text (`author`, `aff`) matches word
  prefixes (`startsWords`), but a known acronym (`acronymOf`, `ACRONYMS` in
  `institutions.ts`) means its institution ("HKU" is not "HKUST").
- Typed text applies, and enters the URL, after a 150 ms pause, the field showing it at once
  (`hooks/use-url-state.ts`, `isTypedChange`, PERF-4); a click applies at once.
- Authors are keyed by name, since Semantic Scholar splits prolific authors into several
  profiles (AFF-H, decision 13). `graph.countPeople` groups a name's profiles (`author_ids`,
  added by the build) that share an institution or a co-author; more than one group of
  `PERSON_PAPERS` papers or more (one-paper profiles are often orphan duplicates) shows
  "2 people?" (`severalPeople`), the papers still counted together.
- `byCitations` and `byGains` (`?sort=citations`, `?sort=rising`) are stable sorts over the
  relevance order: ties keep the best match first with search words, the newest without
  (CIT-6).
- "With code" (`?code=1`, PROD-12, `code.ts`): a linked GitHub or GitLab repository, else
  Hugging Face models or data; a project page (`*.github.io`) or a user's page is not code.
- Venues (`venues.ts`, `components/VenueSelect.tsx`): one, any (`*`), or a family, every
  edition (`CVPR*`, SRCH-15; a workshop's family is its own), which `venueFacets` lists
  before its editions when more than one is loaded. Subjects (SRCH-9, `subjectsOf`): primary
  or cross-listed (`subjectFacets`). Both facets count every loaded paper, not the results;
  the subject select shows the code (`cs.RO`), the URL the name.

## The list views (`app.tsx`, `view-model.ts`)

- `App` holds the state; `viewModel` works out once what a view shows and offers (DEBT-2):
  archive years or days (`showsArchive`), its order and sorts, its toggles. "Hide seen" is
  the Papers view's; "Show abstracts" that of Papers and Highly cited (PROD-14; the reading
  list always shows them); Export that of those two and the reading list (SRCH-16).
- Star sorts (PROD-18): Most starred (`?sort=stars`, `byStars`) once the loaded papers have
  stars, a repository shared by several papers (`shared`) ranking with the unstarred; Rising
  stars (`?sort=rising-stars`, `byStarGains`) once some gained stars in the week
  (`code.gained`). Before, they fall back to the view's own order and to Most starred, as
  Rising does to Most cited. `codeBadge` shows the stars, their weekly gain, "shared" or the
  Hub's likes, explained in a tooltip and to screen readers.
- A folded card rises under the pointer (`--shadow-raised` and a darker border, the only
  sign in the dark theme) and a click opens it (`openOnClick`, UX-34), except on its links
  and controls or after selecting text; an open card ignores clicks so its text can be
  selected (Less, `o` or Enter fold it). More is last in every row of actions
  (`.paper__more`, UX-50), in the same place on every card. Where the browser animates to
  `auto` (`interpolate-size`, Chromium; others open it at once), a card opens smoothly
  (UX-52): its abstract unfolds in 0.24 s from its three lines (`calc-size`), or from
  nothing with the abstracts hidden (`@starting-style`), the error link and the comments
  fade in, and the cards below slide. It folds at once; a shared link's paper is open from
  the start, centered as it stays; nothing moves under `prefers-reduced-motion`.
- In Highly cited a card shows its rank (`viewModel().ranked`, `.paper__rank`), the first
  three in `--medal-gold`, `--medal-silver`, `--medal-bronze`; "Rank 1" for screen readers.
  A card in its year's top 1%, 5% or 10% by citations says so ("Top 1% of 2017",
  `cohortBadge`, decision 22), from `cohorts.json`, which the build puts into the site's
  `index.json` (`withCohorts`: a kilobyte rather than a request); never for the current year
  or without a count.
- Saving from a card (a change of `saved`, not a card drawn saved) bursts (UX-37), and
  `flyToReadingList` flies a star to the Reading list tab with the Web Animations API,
  styled from code as the CSP allows, while the tab is in sight. `prefers-reduced-motion`
  removes the burst, the flight and the rising card.
- A card's footer (UX-28): facts (venue, day, citations, subject), then actions as neutral
  badges, so that the facts keep the accent, each with an icon (`components/icons.tsx`). A
  link that names a site has its logo (DOI; Code by `codeHost`, pinned for both languages by
  `code-cases.json`): Simple Icons' (CC0) in `currentColor`, since a brand color would
  vanish in one theme. Every icon is `aria-hidden`: a control's name stays its text.
- Components: `Topbar`, `ResultsHeader`, `ListNotices` (news since the last visit, warnings,
  filters, feed), `NoResults` (why empty, remedies), `SiteFooter` (sources, `Attribution`,
  also in the graph's ⓘ: REL-10). When nothing matches, `NoResults` offers more papers: in
  Papers the longest preset, in Highly cited all its years and its last 12 months when it
  shows fewer ("No highly cited paper of 2017 matches", UX-55); then, from either, the
  search of every stored paper with the same words, as the period picker's iridescent chip.
- The lists look as the graph (UX-33). The sidebar stacks its chips: the papers' source
  (`PeriodPicker`, `ArchivePicker`), then the filters, each named by its placeholder, its
  `title` and for screen readers, selects with `SelectChevron`, fields bordered with
  `--border-strong` (WCAG 1.4.11). A view's notes (what it shows, affiliation coverage, the
  counts' date) are behind the ⓘ by its count (`ViewNotes`, `InfoButton`); stale counts are
  also said above the papers. The search field's ⓘ holds its syntax and keys
  (`#search-hint`, its description). One `Segmented` draws the orders, Rankings' controls
  and the graph's Size by.
- The sidebar folds on a wide screen (UX-35, `SidebarToggle`, `aria-controls="sidebar"`):
  the grid column narrows (`.content--folded`, children clipped, not squeezed), then hides
  (`visibility`, out of the tab order); a badge counts the filters set
  (`activeFilterCount`); the choice is remembered (`loadSidebarFolded`). Under 821 px the
  sidebar stacks above the papers, its filters in `<details>`.
- `components/ErrorBoundary.tsx` (TEST-10): a view that fails to draw says so (Reload, start
  over, the correction contact), the tabs and sidebar still usable, and draws again when the
  state or the papers change (`resetKeys`); a last one wraps the app.
- Print (`@media print`, UX-18): cards in black on white, none split by a page break, each
  with its arXiv address and its open abstract whole; no controls, sidebar or graph; a
  folded card keeps its "+N". Only the cards loaded print.
- Text sizes are in `rem` (UX-16) so the reader's font size scales the page, none under
  11 px at the default 16 (`tests/styles.test.ts`). Standalone controls have a pointer
  target of 24 px at least (WCAG 2.5.8; ⓘ through a pseudo-element); names in a card's lines
  are text, exempt, and checkboxes have labels.
- Dates and numbers are British English whatever the locale (`LOCALE`, `locale.ts`, UX-17:
  "25 Sept 2026", "10,000"); counts go through `countOf` (UX-25).

## URLs and history (`url-state.ts`)

- Every view is a shareable URL. A navigation step (`isNavigation`: another view, paper,
  period, year, category, or a filter set by a click) adds a history entry; typing and
  sorting replace it.
- The top bar (UX-32) spans the window, the tabs outside the views' column so they stay put;
  it keeps one line down to about 950 px. Under 640 px the tabs other than the current one
  show their icon alone (UX-31), labelled for screen readers.
- Tabs are links, `?paper=` included. `paperLink` sends an archived paper (no day file) to
  its Highly cited year, and a last-12-months paper older than the oldest day file to that
  range (`archiveRangeOf`). Share copies the link and changes nothing else.
- Parameters, all optional (`readState`, `writeState`): defaults are left out; an unknown
  `view`, `sort`, `range`, `year`, `cat`, `xl` or `code` reads as the default, an unknown
  `subject` or `venue` is kept and matches nothing. `tests/url-state.test.ts` fails when a
  parameter the code reads is missing here.

  | Parameter | Holds | Default | Read by |
  | --- | --- | --- | --- |
  | `q` | The search words | none | every list, Rankings, the graph |
  | `cat` | The category | the store's first | every view |
  | `from`, `to` | A period of days (`from` alone: one day) | `range` | Papers, the graph and Rankings without `year` |
  | `since` | The days since a day, to the latest (PROD-13) | `range` | the same |
  | `range` | `day`, `week`, `month` (old links' `1`, `5`, `20`, `40`, `all` open the one holding as many days) | `week` | the same |
  | `scope` | `all`: every stored paper, the period aside (PROD-21); a period chosen or another view leaves it | the period | Papers |
  | `sort` | `relevance`, `newest`, `citations`, `rising`, `stars`, `rising-stars`, `custom` (UX-39) | `relevance` (`custom` in the reading list without search words) | the lists |
  | `view` | `papers`, `cited`, `graph`, `trends`, `rankings`, `reading-list`, `about` | `papers` | every view |
  | `paper` | An arXiv id: the paper opened (a list) or selected (the graph) | none | the lists, the graph |
  | `year` | `2017`, `2019-2021`, `all`, `last-12-months`; years the archive lacks are corrected in place (`correct`, SRCH-20) | latest year in Highly cited, recent days elsewhere | Highly cited, the graph, Rankings |
  | `focus` | A graph node id (`institution:mit`): its papers alone | none | the graph (other views drop it) |
  | `rank` | `author` (SRCH-13) or `country`, on a world map (UX-41) | institutions | Rankings |
  | `metric` | `papers`, `citations`; for countries also `per-million`, `impact` (highly cited only) | citations for highly cited papers, else papers | Rankings |
  | `folder` | A reading list folder (UX-38), in its links only; a name this browser lacks shows every saved paper | every saved paper | the reading list |
  | `#folder=…&papers=…` | A shared folder's fragment (UX-46): its name and arXiv ids | none | the reading list |
  | `window` | `year`: the last 12 months against the 12 before (PROD-20); a change replaces the entry | `quarter` (90 days against a year before) | Trends |
  | `topic` | A topic key (`world model`, `vla`): the one opened; a history step | none | Trends |
  | `compare` | Topic keys drawn by the explorer, comma-separated, five at most; a change replaces the entry | none | Trends |
  | `by`, `at` | An author or an institution, as clicked: that name only | none | the lists, Rankings |
  | `author`, `aff` | Typed author or affiliation text: word starts | none | the same |
  | `venue` | A venue (`ECCV 2026`), a family (`ECCV*`) or any (`*`) | none | the lists, Rankings, the graph |
  | `subject` | A subject, primary or cross-listed (`Machine Learning (cs.LG)`) | none | the lists, Rankings |
  | `xl` | `0`: cross-lists hidden; no control sets it, old links and saved searches do (its chip clears it) | shown | the lists, Rankings |
  | `code` | `1`: papers that link their code | all | the lists, Rankings |

## Periods and loading (`period.ts`, `data.ts`, `hooks/use-papers.ts`)

- Periods (`components/PeriodPicker.tsx`): a preset (`?range=`: `day`, `week`, `month`, in
  calendar days back from the latest announcement day, so a week holds five announcement
  days, fewer after a holiday; SRCH-14), dates (`?from=&to=`), or the days since a day
  (`?since=`, PROD-13: a bookmark that new days join). Old presets open the one holding as
  many days (`rangeOf`).
- The calendar works from the keyboard (UX-14): Tab reaches one day, arrows move a day or a
  week past the days without papers (`stepDay`), Enter picks, a focused day previews the
  range. Its button ("Period: …", "Papers: …" in the graph, `compact`) is muted when highly
  cited papers show instead (`source`).
- Papers are downloaded and indexed in the browser: a period's latest days whole, within
  `PAPER_BUDGET` (10,000; a year of cs.CV, 46,000, takes about 480 MB to index, which
  crashes phones), its older days from the search shards within `LIGHT_BUDGET` (20,000 more,
  `lightDays`, PERF-1), without abstracts, so about seven months are searchable. The picker
  says which days have their abstracts searched and what both budgets leave out.
- A failed day file is asked for once more, then left out, as are the days of a failed month
  shard, named in a notice with Retry (`missingDays`, `formatMissingDays`, SRCH-10); only a
  period whose every day file fails is an error. A shard's paper loads its day file when its
  card opens or on "Load the abstract" (`hooks/use-whole-paper.ts`, `loadWholePaper`); the
  reading list keeps its `light` and `code_url`, checked as the build writes them (SEC-2).
  The smoke test builds with `VITE_PAPER_BUDGET=3` so that a day comes from a shard.
- All stored papers (`?scope=all`, PROD-21, `store-search.ts`): "All papers", a choice of
  the Papers view's period picker, the four alike two a row; its button then names it, and a
  preset or a day leaves it; also a remedy when nothing matches. Its icon and an iridescent
  border set it apart (`--shimmer-1` to `4`, a conic gradient turned by `@property`), as
  Claude's ultracode button: chosen, the border turns, and every six seconds a light crosses
  the button under its text while its name shines, eased; it glows once when chosen; out of
  sight it rests (`IntersectionObserver`); nothing moves under `prefers-reduced-motion`.
  Every day file, `top-recent.json`, then each archive year, newest first, four read ahead
  (`searchStore`), each file's papers kept only while `candidateTest` reads them: memory
  holds what passes, not the store. The test lets through every paper the index would find
  (a test checks it): the filters, and each word in the folded text, or, for a word a typo
  may match (7 letters or more), a half of it and then a word of the paper one edit from it.
  5 µs a paper against 175 µs to index it. What passes, `PAPER_BUDGET` at most (newest
  first; the others counted, said above the list), is indexed and searched as a period; the
  count is of the distinct papers read. A word or a filter is needed: without, a notice asks
  for one. While it reads, the count line says how far, and how many papers passed the test
  ("Searching… 42% · 1,204 papers may match", a phone's line), twice a second at most, files
  coming twenty a second; screen readers hear "Searching every stored paper…" once, not each
  step (UX-51). Its code loads with the first such search (1 kB; the button and notices,
  2.4 kB on the landing page, which PERF-17 made room for). On 2026-10-27 (30,842 papers,
  21.6 MB compressed the first time, then the browser's cache, which asks after ten minutes
  whether each file changed), the built site served locally, in Chromium: 1.2 to 1.7 s for a
  narrow search ("nerf", "kaiming he"), 2.8 s for "detection" (5,171 found), 3.2 s for
  "image" (past the budget); 3.5 to 12 s with the processor four times slower. Pages adds
  the reader's bandwidth and a round trip a file (55 files, about 270 in a year). In a
  background tab, the browser's timers slow it to a crawl.
- `index.html` preloads `data/index.json` (`<link rel="preload" as="fetch" crossorigin>`);
  `loadIndex` reuses that response only because it fetches it in the same mode and
  credentials: keep the two in step (PERF-14; the smoke test checks the single request).
- Other data files are fetched as `<path>?v=<version>` (`dataUrl`, PERF-8): the build writes
  the first ten hex digits of each loaded file's SHA-256 into the site's `index.json`
  (`versions`, `tooling/data-versions.ts`), since Pages lets browsers cache a file ten
  minutes and a deploy could otherwise mix a fresh index with stale shards. Paths stay the
  store's; the index is never versioned, nor the development server's files.
- `usePapers` cancels the requests of a period left; `data.ts` keeps loaded files (as many
  papers as a period loads, least recently used out first) and loads again only for another
  period (`periodKey`), so Back to the same period keeps the index.
- Highly cited (`?view=cited&year=`) loads archive years ranked by citations (one, a range,
  `all`; by default the latest), chosen in `ArchivePicker` (`components/ArchiveYears.tsx`,
  UX-33). Past `PAPER_BUDGET` papers it keeps the best by citations per year of age, the
  archive's score (`archive-years.ts`, `bestRanked`), and says how many it leaves out
  (PROD-17). The graph and Rankings show archive years when the URL has a `year`; the tabs
  carry it from Highly cited, the Papers tab clears it. The papers of a graph or Rankings of
  archive years open in Highly cited over the same years.
- `year=last-12-months` (PROD-11): the 1,000 most cited papers of the last 12 months, kept
  by the weekly archive in `top-recent.json` ([archive.md](archive.md)), since the store
  holds nothing else older than the day files. `ArchiveRange` is a `YearRange` or
  `LAST_12_MONTHS`, offered once the index has `top_recent` (`shownYears`). Their counts are
  in the year shards, and the build merges `scholar.json` into the file (`paperFiles`,
  `PAPER_FILE_RE`).
- While loading, the header and the graph say what loads, from the index's counts
  (`loadingLine`, over the days `selectDays` keeps). A failed load is an alert with Retry,
  which loads again what failed (UX-6); `loadErrorMessage` reads "Failed to fetch" as "the
  network or the site did not answer".

## What the build derives from `data/` (`vite.config.ts`, `tooling/`)

`vite.config.ts` serves `../data` at `/data` in development and copies it into `dist/` on
build (without dotfiles and `.tmp` files), deriving in both what only the site uses. The
pipeline and `validate` never see these. `base: "./"` keeps the site working under
`user.github.io/<repo>/`.

- **Citation shards** (`tooling/citation-shards.ts`, `src/citations.ts`): `citations.json`
  by month for the day files and by year for the archive
  (`<category>/citations/2026-09.json`). `hooks/use-citations.ts` loads those of the papers
  shown and of the reading list, once a page (`citationShard`): 11 KB gzipped for the recent
  days instead of 125 KB. A failed one shows no counts and is asked for again when next
  needed (SRCH-10). A paper of a day file and of the archive is in both shards. Shards carry
  the gains of `citation-gains.json` (`gains`): "+12 this week" (`gainLabel`) and Rising
  (`byGains`, CIT-9), offered once gains exist.
- **Search shards** (`tooling/search-shards.ts`, `src/search-shards.ts`, PERF-1): the
  day-file papers by month (`<category>/search/2026-09.json`), as the site gets them but
  without `abstract` and `comments` (about 6 MB gzipped a year), plus `code_url` and `light`
  (the day file holding the whole record); each loaded once a page, never cancelled, and
  kept apart from the cached day files, which a month would push out.
- `tooling/scholar.ts` adds `doi`, and the published `venue` where the comments name none,
  from `scholar.json`; `tooling/code.ts` (PROD-18) adds `code` from `code.json` only where
  the record's link is still its card's (`codeUrl`); `withSiteFields` merges both, in
  development too.
- **Atom feeds** (`tooling/feeds.ts`, `src/feeds.ts`):
  `feeds/<category>/institutions/<slug>.xml` for every institution of the day files and
  `feeds/<category>/venues/<venue>.xml` for `MAJOR_VENUES` (no workshops): the papers of the
  last 60 days (`FEED_DAYS`), at most 30 and 100. The slug is the `searchKey`, hyphenated,
  so `feedOf` finds the feed of a filter. An institution keeps its feed while the store
  holds one of its papers, empty after 60 quiet days. `PREPRINT_RADAR_SITE_URL` gives ids
  and `self` links (a local build: `urn:` ids). The window keeps the feeds near 20 MB.
- `noThirdPartyLoads` (`tooling/third-party.ts`) fails the build if the site would load
  anything from another origin (links are fine), as About promises; the one exception is
  Cloudflare Web Analytics, given its token.
- `landingBudget` (`tooling/landing.ts`) fails the build past `LANDING_BUDGET` (100 kB
  gzipped, PERF-15; 75 until PERF-18). What the list never shows loads through `lazyView`
  (`components/lazy-view.tsx`: one request, a notice meanwhile, Reload on failure): the
  graph (PERF-13), the world map, Trends, About, Rankings' tables with their graph model
  (`rankings.ts`, `graph.ts`; `RankingsControls.tsx` stays eager), the folders and the
  shared-folder notice, Highly cited's years (`ArchivePicker`, PERF-17); the CSV, RIS and
  Markdown exports come with the first (`export.ts`), the search of every stored paper with
  its first (`store-search.ts`). The deploy measures a little more than a local build (its
  analytics tag, absolute links): build with `PREPRINT_RADAR_SITE_URL` and
  `PREPRINT_RADAR_ANALYTICS_TOKEN` set to know its figure.
- `contentSecurityPolicy` (`tooling/content-security-policy.ts`, SEC-1) adds a CSP meta
  (Pages sends no headers): the site's own scripts, styles, data, images and worker only, so
  third-party text can never run a script. No inline script (`public/theme.js` sets the
  theme); styles are set from code through the CSSOM, never as `style` attributes in HTML.
  The smoke test checks nothing is refused; the development server has no policy.
- **Visits** (UX-47, `tooling/web-analytics.ts`): Cloudflare Web Analytics, only when the
  build gets `PREPRINT_RADAR_ANALYTICS_TOKEN` (a repository variable, public anyway, passed
  by `deploy.yml`). The build appends `beaconTag`, and the policy allows its script and
  report address only (`contentSecurityPolicy(true)`). No cookie, nothing stored; it reports
  the page's address without query or fragment, the referrer and the browser, Cloudflare
  adding the country. About says so when the page holds `script[data-cf-beacon]`. A
  malformed token fails the build; deleting the variable stops counting.
- **The logo** (UX-48, `logo.ts`, `components/Logo.tsx`): the designer's files in `public/`.
  The top bar inlines the lockup, 32 px high, to take the text color and the accent in both
  themes, named once by its `aria-label`. Its paths are never redrawn or optimized:
  `tests/logo.test.ts` compares them with the files, which Biome skips (`!public/*.svg`).
  Never under 24 px high; below, the mark alone.
- **A shared link's card** (UX-49, `tooling/share-card.ts`): Open Graph tags and
  `public/share.png` (1200 by 630, from the designer's file with `rsvg-convert` and
  ImageMagick), absolute when the build knows `PREPRINT_RADAR_SITE_URL`. Previews run no
  script and the site is one page, so every link shows that card. On a coarse pointer, Share
  opens the system share sheet (`native-share.ts`, Web Share API); elsewhere, or when it
  fails, the link is copied.

## In this browser only

- **Reading list** (`reading-list.ts`, `hooks/use-reading-list.ts`): stored and exported as
  `{version: 1, papers}`, older bare arrays still read. Every entry goes through `toPaper`:
  a bad one is skipped, its arXiv and PDF links rebuilt from its id, an HTML link kept only
  on arxiv.org (SEC-2). Import merges by id; other tabs follow through `storage` events; a
  loaded day's fresher record replaces the saved one; a refused save is said, not swallowed.
- **Folders** (`folders.ts`, `hooks/use-folders.ts`, `components/Folders.tsx`, UX-38):
  stored apart (`preprint-radar:reading-folders`, `[{name, papers: [arXiv ids]}]`) and
  exported in the same file; a paper can be in several (UX-45, `addPaper`, `removePaper`).
  Names are trimmed, cut to 60 characters and unique whatever their case; imported folders
  (`readFolders`, arXiv ids only) merge by name. A folder exports alone (UX-44,
  `folderFile`). The sidebar lists them with counts (`?folder=`), renamed in place or
  deleted after an inline confirmation (the papers stay saved); a card's `FolderMenu` files
  its paper, and unsaving it removes it from every folder (`forgetPaper`).
- **A folder shared by a link** (UX-46, `share.ts`, `hooks/use-shared-folder.ts`,
  `components/SharedNotice.tsx`): Share copies a link with its name and arXiv ids in the
  fragment (at most `MAX_SHARED`, 1,000), which browsers never send, so the list never
  reaches GitHub's servers; a refused clipboard shows the link. The fragment is untrusted
  (`readShare`: the name cleaned, arXiv ids only). The papers are found by id
  (`data.loadPapersById`): in the search shards of the id's month and the next
  (`candidateMonths`), the archive's years (`candidateYears`), then the last 12 months; one
  not held is named with its arXiv link, as is a paper cross-listed months after its
  submission (rare; loading every month's shard would cost about 0.9 MB each). "Add to my
  reading list" copies them into a folder of that name: a folder kept in common would need a
  server.
- **The reading list's own order** (UX-39, `?sort=custom`, `viewModel().custom`): its
  default without search words. A card is dragged by its handle (`.paper__grip`, `draggable`
  only while pressed, so a drag on its text still selects; shown with `hover: hover`) before
  or after the card under the pointer (`movePaper`); Alt+↑ and Alt+↓ move the focused card,
  which keeps the focus; with a search or a folder, a move places it by the neighbours
  shown. Dropped on a folder (`PAPER_DRAG_TYPE`), a paper joins it; on All saved, it leaves
  the folder shown.
- **Saved searches** (`saved-searches.ts`): the query string of their words and filters, so
  that they run on any period, with their papers new since the last visit counted. Save is a
  toggle (UX-59): saved, it reads "✓ Saved", muted and pressed, and keeps the focus; pressed
  again, it forgets the search. The saved search shown is pressed in the list, as the
  reading list's folder shown; the row just saved arrives with a bump (not those there when
  the list first draws), and each count of new papers pops as it arrives.
- **The list** (`components/PaperList.tsx`, `paging.ts`) adds `PAGE_SIZE` (40) cards as its
  end comes into view and starts over only for a new list (`listKey`). A card that leaves
  (seen while seen papers are hidden, unsaved from the reading list) does not collapse the
  list: the next card takes the focus; the paper a link opened (`?paper=`) stays until
  folded. A "+N" opens its card and focuses the first name it shows. Late counts re-rank the
  list only when its order uses them (UX-23).
- **Triage** (`triage.ts`, `hooks/use-triage.ts`), never in the URL: seen papers per
  category, pruned to the last `SEEN_MONTHS` (3) of identifiers, for "Hide seen" (counted in
  the header, and an empty list's reason, UX-26); the previous visit's newest day, fixed for
  the session, for the "new papers since your last visit" banner, and in Papers' days for a
  "New" by the headings of the days after it and a rule where they end, "Already here at
  your last visit" (UX-54), only where both kinds of day are shown. Every list says its
  end ("End of the list · 31 papers") once its last page is drawn, folded days aside. The
  keys j/k/o/s/x and `/` pass `keyboard.ts`'s typing guard, so the search box has no
  autofocus; Escape leaves it.
- **Preferences** (`preferences.ts`) live in `localStorage`. The theme
  (`hooks/use-theme.ts`) also colors the browser's bar (the `theme-color` metas,
  `theme-color.ts`, `public/theme.js` before first paint), which `tests/styles.test.ts`
  checks (UX-18).

## Withdrawn papers, old ones announced lately, and dates by month

- A paper whose comments say it was withdrawn carries `withdrawn`: its card shows a
  Withdrawn badge, and the pipeline keeps it out of Highly cited (decision 18).
- A paper announced 12 months or more after its identifier's month (an old paper
  cross-listed lately) says "first version 2019" (`firstVersionYear` in `format.ts`,
  PROD-14); old-style identifiers ("cs/0601001") are not read.
- A paper announced before the index's oldest day shows its month alone, "Mar 2021", with a
  tooltip saying why (`formatAnnounced`, META-5): arXiv's catalog dates it by its first
  version or its identifier's month, not its announcement. Once pruning deletes day files,
  their archived papers are dated by month too. Sorting and exports keep the stored date.

## Exports and corrections

- `export.ts` writes the results shown as CSV, RIS or Markdown, `bibtex.ts` as BibTeX (a/b/c
  on colliding keys, LaTeX escaping, case-protected words), citing the published DOI when
  known, else arXiv's. The reading list's Import library and Export library carry the whole
  list, its folders and saved searches to another browser (a JSON file).
- A card's BibTeX copies its entry, Share its link (a phone's share sheet, UX-49). A copy
  keeps the badge's name and width, so that its neighbours stay (UX-53): its icon turns to a
  check and a tip rises above it for 1.5 s, the key to cite (`\cite{chen2026r4dgs}`,
  `citationKey`) or "Link copied", which screen readers hear from the card's status line.
  A refused clipboard downloads the entry and says "Downloaded".
- `components/About.tsx` (`?view=about`): the data sources, the correction contact and the
  privacy note; keep it true when the pipeline or the app changes. Its link and each card's
  "Report an error" open a mail with a template (`report.ts`).

## Trends (`components/Trends.tsx`, `trends.ts`, `LineChart.tsx`, `chart.ts`)

- The topics of the titles that rise, cool and are new (PROD-20), from `trends.json`
  (`docs/trends.md`; `loadTrends`, `null` until written, which the view says).
- Two windows (`?window=year`): the last 90 days against the same days a year before
  (`quarter`), or the last 12 months against the 12 before. Rising and Cooling follow the
  pipeline's order, each row with its lift (`lift`: both shares smoothed by the window's
  `added` share, so the figure follows the order), its papers then and now and a sparkline;
  New by papers. Ten rows, then Show all; side by side from 981 px.
- A row opens its topic (`?topic=`, a history step) above the lists, focused when opened
  from them: its papers and share, its impact (the share of its papers among the most cited
  tenth of their month: 10% for an average topic), its share chart, its most cited papers,
  and links to its papers in Papers and Highly cited. These search each phrase singular and
  plural, synonyms included (`topicQuery`), since a quoted phrase matches whole words.
- The explorer draws any topic of `topics.json`, single words too, loaded (`loadTopics`,
  400 kB gzipped) only when its field is focused or the link names topics (the smoke test
  checks it); found by word starts (`findTopics`), drawn as quarterly shares (`quarterly`),
  up to `COMPARED` (5). Lines take `--series-1` to `--series-5` and keep their color while
  others come and go (`assignSlots`); the topics drawn are the legend.
- A search naming a listed topic gets a note above Papers and Highly cited (`useTopicNote`,
  `topicNote`: the 90 days' lists, then the 12 months'). `topicsOfQuery` takes the first
  quoted phrase, else the words, the last keyed as the pipeline does (`lastWordKey`: an
  acronym loses only a plural "s", other words are made `singular`;
  `tests/fixtures/singular-cases.json`, read by both test suites); `topicEntry` maps
  synonyms. `trends.json` is fetched once a search is typed (`trendsOf`).
- `--trend-rising` and `--trend-cooling` mark rows and lines, never text. `LineChart` shows
  a crosshair and a tooltip at the point nearest the pointer or the arrow keys (`xScale`,
  `niceTicks`), styled from code, and "Show as a table" for screen readers.

## The graph

- `graph.ts` (pure, tested) builds three layers: papers, institutions, authors. With papers
  on, a paper links to its authors, an institution to the authors the paper places there,
  else to the paper (never to an unplaced author); a name listed twice is one author
  (AFF-21). With papers off, it is the co-occurrence projection, but a paper of more than
  `MAX_CLIQUE_AUTHORS` (50) authors links them only to its institutions (PERF-3, decision
  15): one 561-author paper made 39% of a year's author links. Nodes are keyed by the
  `searchKey` of the pipeline's canonical name, so a company is one node across its ROR
  entries (`rorId`). Default: papers and institutions, no isolated nodes.
- `components/GraphView.tsx` holds the state and drives the renderer, with `GraphDetails`
  (the node selected, `nodeConnections`), `GraphLegend`, `GraphFilters`,
  `GraphSettingsPanel` (DEBT-3), `GraphFind`, `GraphInfo` and `GraphTimeline`.
  `graph-layout.ts` gives start positions (each component together, on a spiral);
  `graph-renderer.ts` draws on a canvas and handles the pointer. The view is full screen,
  and a chunk of its own (`components/LazyGraphView.tsx`, PERF-13).
- The controls float on the canvas (UX-29), which papers (the URL's) apart from how to draw
  them (this browser's). Top left, chips choose the papers (period, highly cited years,
  venue, words); the Find field (`/`) and the selected node's details below (a bottom sheet
  on a phone); Find's last row filters the papers instead of highlighting. Top right,
  `GraphSettingsPanel`: Nodes (layers, thresholds, isolated nodes, Limit), Appearance (Size
  by, node size, Labels, `labelThreshold` reversed), Layout (forces, Reheat), Reset, and the
  exports: PNG (`GraphRenderer.toPng`) and GraphML for Gephi, Cytoscape or NetworkX
  (`graph-export.ts`). `GraphInfo` gives the affiliation coverage, with a caveat below half
  (`affiliationCoverage`, PROD-16), the attribution and the counts' date (REL-10). The
  time-lapse player is absent for a single day; the mouse hint shows from 1,280 px wide,
  where it leaves the player room.
- The layout runs in a module worker (PERF-2): `graph-simulation.ts` is d3-force without a
  DOM (tested in Node); `graph-worker.ts` posts positions as a transferred `Float32Array` at
  most once a frame, numbered by graph so a former graph's late positions are dropped. A
  dragged node is pinned in the worker. Under reduced motion the layout runs to rest at
  once. The canvas's `data-layout` (`moving`, `settled`) is what the smoke test waits for.
- Citations arrive later and are added apart (`withCitations`, PERF-7): a graph with the
  same layout (`sameLayout`) is new counts, not a new graph; nodes sized by citations grow
  (alpha 0.3), sized by papers nothing moves.
- Equilibrium without Reheat (UX-30; `COOLING` in `graph-simulation.ts` holds the
  measurements): a new graph cools without collisions and with little friction
  (`velocityDecay` 0.1) in 530 ticks up to 2,500 nodes, fewer above in proportion
  (`coolingDecay`, at least 80), then a short pass with collisions (alpha 0.1). A layout at
  rest that moves again (Reheat from 0.5, new forces, a mostly laid-out graph at 0.4)
  settles with d3's decay and friction (`SETTLING`). The cooling is hidden above alpha 0.3
  (`Layout.hidden`), while the start spiral bursts open: the canvas keeps its former frame,
  then fades the graph in (`graph__canvas--reveal`).
- Over `LARGE_GRAPH` (2,000) nodes: `theta` 1.2, no collisions, a shorter cooling. Never set
  `distanceMax` nor raise `theta` much: nodes pile up in rings. Small components get extra
  gravity once the largest is big, else its repulsion rings them far off.
- Drawing (PERF-5): a few `Path2D` per frame; the scene in sight is kept while nothing moves
  (`sceneFor`, keyed by `geometry`), so a hover builds only what it lights. A month
  (3,500 papers) is about 5,700 nodes by default, 23,000 with all layers.
- Touch and keyboards (UX-2, decision 14): pinch to zoom (`pinchView`), +, − and Fit
  buttons. Find is a combobox: its first 10 matches listed (arrows and Enter choose one,
  whose details take the focus), Enter and Shift+Enter go through all, counted in a status
  line. The canvas's label counts nodes and links; its description points to Rankings, the
  same data as a table.
- Limit (`maxNodes`) keeps the most frequent institutions and authors, never papers; the
  legend says how many it leaves out (`Graph.eligible`, UX-20). Turning authors on hides the
  authors of a single paper (`authorLayer`), most of the nodes. The time-lapse steps by day,
  or by week or month past 60 steps (`replaySteps`).
- Size by papers (area proportional, `nodeRadius`) or by citations summed over a node's
  papers (`GraphNode.citations`), on a log scale (`citationRadius`), as counts span 0 to
  10⁵; the always-labelled biggest nodes follow it.
- Rankings (`rankings.ts`, `components/Rankings.tsx`): the institutions or authors of the
  papers shown, by papers or citations, named through `buildGraph` to match the graph.
  Institutions rank on the papers with known affiliations: the ⓘ gives their share
  (`format.affiliationCoverage`), and below half the table says the others count for none
  (PROD-16). A column header sorts by it (`SortHeader`, UX-42), with `aria-sort`.
- **The world map** (UX-41, `world.ts`, `components/WorldMap.tsx`, `?rank=country`), loaded
  when chosen (`LazyWorldMap`, 49 kB gzipped). A paper counts fractionally in the countries
  of its institutions with a ROR id (`countries.json`, UX-40), its citations shared alike,
  so a collaboration counts once. Metrics: papers, citations, papers per million people
  (from `MIN_POPULATION`, a million), and impact, citations per paper over every placed
  paper's (from `MIN_IMPACT_PAPERS`, 10; highly cited papers only).
- The shapes are Natural Earth's 1:110m countries in the Equal Earth projection, which keeps
  areas (`src/geo/world.json`, written by `tooling/world-map.ts`); countries too small are
  dots at their 1:50m label points. Classes (`--map-s0`…`--map-s5`; `--map-d0`…`--map-d4`
  for impact, on fixed `IMPACT_THRESHOLDS`; hatching without a value), the volume metrics'
  classes on a log scale (`logThresholds`), as a few countries hold most papers. The table
  under the map holds its values for the keyboard and screen readers, and pins a country by
  name.
- Flat or a globe (UX-43, `components/MapFrame.tsx`, `map-view.ts`, `loadMapGlobe`). The
  flat map zooms up to `MAX_ZOOM` (8×); the globe (`geoOrthographic`) turns by a drag and to
  a country pinned (at once under reduced motion), projected again at most once a frame.
  Both zoom by the buttons, a pinch or the wheel with Ctrl or ⌘ (`wheelFactor`): the wheel
  alone scrolls the page, as does a finger (`touch-action: pan-y`) but on a zoomed map. A
  tooltip points at a country's largest part (`anchorOf`).
- A connection in the details lists, on a click, the papers its link stands for
  (`linkPapers`: in the projection, those that link the two). "Focus on this"
  (`papersOfNode`, `?focus=institution:<key>`) shows the graph of a node's papers alone; the
  id matches as nodes are keyed, a node not drawn is named by `nodeLabel`, a focus without
  papers among those shown says so, and other views drop it.
