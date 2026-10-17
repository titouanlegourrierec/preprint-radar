# The web app: how it works

The design of `web/` module by module: search, URLs, triage, periods, the views and the
graph, and what the build derives from `data/`. Read the part you touch before changing
it; the tests pin most of it (`web/tests/`, the smoke test in `web/e2e/`).

## Search (`search.ts`, `highlight.ts`)

- MiniSearch over title, authors, affiliations and their institutions, venue, abstract and
  comments, each weighing as `FIELD_BOOSTS` says: the title 3, authors 2, affiliations
  and venue 1.5, the abstract 1, comments 0.5. Only the last word typed matches as a prefix, from 4 letters, so that acronyms
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
- An uppercase `OR` joins the word or phrase on each side (SRCH-6): `nerf OR "gaussian
  splatting"` finds either, `video nerf OR gan` video, and nerf or gan; a lowercase "or" is
  a stop word, an `OR` with nothing to join is nothing, and an exclusion stands alone.
  `parseQuery` groups the alternatives (`either`), `queryTree` asks MiniSearch a tree:
  all of the free words, one alternative of each group (a phrase's words all, its order
  checked afterwards by `holdsEither`). Only the word being typed is a prefix, an
  alternative or the last free word. No field prefixes (`title:`): the recommendation of
  2026-10-17 kept to `OR`.
- Relevance favors the papers that hold a query's words side by side (SRCH-18,
  `adjacentPieces`): each two words that follow each other in the query, with the stop
  words between them and the last one as a prefix ("text to image", "image generation"),
  as patterns over the folded text of its searched fields, built once a paper (`fold`
  only lowercases ASCII text, five times faster, which most is); a paper holding all of
  them scores three times as much
  (`ADJACENCY_BOOST`), so that "text-to-image generation" in an abstract ranks before the
  three words apart, but not before them in a title. The top 20 results of 17 queries of
  two or more words held them as typed 84% of the time, 95% with it. A first search of 975
  results takes 13 ms instead of 5, 7.5 ms again.
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
  link (`codeBadge`: a star and "1,234", "+12 this week", "shared"; a heart and "23" for the
  Hub's likes, both drawn icons since UX-36),
  with what they are in its tooltip and for screen readers.
  Each paper is a card on the page's background (UX-34), as the graph's floating panels:
  rounder than the fields (`--card-radius`, 18 px), a squircle where the browser draws one
  (`corner-shape: squircle`, with a radius of 32 px, which its flatter corners need to
  look as round), and so is Rankings' table; printed, they are rows under a rule again.
  A folded card rises under the pointer (`--shadow-raised`, its border darker, which is
  the only sign in the dark theme; no motion with `prefers-reduced-motion`), and a click
  on it opens it as More does (`openOnClick`), but on its links and controls or after a
  drag that selected text; an open card ignores clicks, so that its text can be selected,
  and Less, `o` or Enter fold it.
  In Highly cited (`viewModel().ranked`), a card says its rank in the order shown before
  its title (`.paper__rank`): its position among the results, whatever the search and
  filters keep and whether by citations, gains or stars, the first three in gold, silver
  and bronze (`--medal-gold`, `--medal-silver`, `--medal-bronze`, with `--medal-text` on
  them in either theme), the others a neutral pill; "Rank 1" for screen readers.
  A paper saved from its card, by the star or the `s` key (a change of `saved`, not a
  card drawn saved), bursts (UX-37): the star pops, a ring and eight sparks spread from it
  (`.save-burst`, angles by `nth-child`), and `flyToReadingList` flies a copy of the star
  to the Reading list tab (`data-tab="reading-list"`) with the Web Animations API, placed
  through `style` from the script, which the Content-Security-Policy allows (the smoke test
  saves a paper under it); the tab's star bounces as it lands (`.tab--bump`). The flight
  only while the tab is in sight, the bar scrolling away with the list; none of it under
  `prefers-reduced-motion`.
  A card's footer has two rows (UX-28): what it says of the paper (`.paper__meta`: venue,
  day, citations, subject), then what it offers (`.paper__actions`), each link and
  control a badge (`.action`) with an icon before its name (`components/icons.tsx`).
  The badges are neutral (surface, border, text color) so that the facts above keep the
  accent; More is one without its outline, Seen pressed is filled, and the stars are the
  second part of the Code badge (`.action-group`, the count not a link). An icon is the
  site's logo where the link names one (DOI; Code by `codeHost`, GitHub, GitLab or
  Hugging Face, the pipeline's own hosts, which `code-cases.json` pins for both),
  otherwise one drawn here (PDF, HTML, BibTeX, Share, Graph, Seen, More). The logos are
  Simple Icons' (CC0), copied in, in one color (`currentColor`): a brand's own would
  vanish in one theme. Every icon is `aria-hidden`, so a control's name stays its text.
  The authors and the affiliations each follow an icon too (people, a building;
  `.paper__line`), their lines wrapping beside it, the icon one line high (`1lh`).
  "Hide seen" is the Papers view's alone, "Show abstracts" that of Papers and Highly cited
  (PROD-14; the reading list always shows them), and the Export menu that of Papers,
  Highly cited and the reading list (SRCH-16).
  The rendering is in components: `Topbar` (the tabs), `ResultsHeader` (the count and
  its ⓘ, the sort control or Rankings' own, the toggles, the Export menu and the reading
  list's tools), `ListNotices` (news since the last visit, warnings, the filters set, the
  feed), `NoResults` (why a list is empty, and its remedies) and `SiteFooter` (the
  sources, `Attribution`, which the graph's ⓘ shows too: REL-10).
- The lists look as the graph (UX-33). The sidebar's controls are the graph's chips in a
  column: the papers' source first (`PeriodPicker`, and in Highly cited and Rankings
  `ArchivePicker`, the graph's two chips as fields of two lines), then the filters, each
  with its icon inside and its name in the placeholder and for screen readers (`title`
  too, a filled field having lost its placeholder), the selects with the chevron of the
  others (`SelectChevron`), the border of a form field kept (`--border-strong`, WCAG
  1.4.11). What a view says of its papers is behind an ⓘ beside the count (`ViewNotes` in
  `InfoButton`, as the graph's `GraphInfo`): what it shows and how its papers are chosen,
  the affiliation coverage and the citation counts' date; stale counts are also said above
  the papers, and Rankings says the coverage beside its count when it is below half. The
  search field has the Find field's magnifier and `/` key, its syntax and the list's keys
  behind its own ⓘ (still its description for screen readers, `#search-hint`), and the
  relevance's ⓘ explains that order. One `Segmented` draws the orders, Rankings' controls
  (in the header, where the lists have their order) and the graph's Size by; fields,
  buttons, cards and notices share the graph's radius (`--radius`, 12 px). The cards' star
  and the theme button are drawn icons (`StarIcon`, filled once saved; a sun, a crescent,
  a half circle for the system's theme).
- On a wide screen the sidebar folds (UX-35): `SidebarToggle`, at the left of the count
  (`aria-controls="sidebar"`), closes its column (`.content--folded`, a transition of the
  grid's columns, the sidebar's children keeping their width so that it clips rather than
  squeezes them), then hides it (`visibility`, out of the tab order); folded, a badge
  counts the filters set (`activeFilterCount`), which the chips above the papers name. The
  choice is this browser's (`loadSidebarFolded`). Under 821 px the sidebar is stacked above
  the papers, its filters folded in `<details>`, and the button is not shown.
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
- The top bar is one across the window above every view, the graph's (UX-32): the site's
  name on the left, the tabs on the right, outside the views' centered column, so that the
  tabs stay in place from one view to the next. No rule under it: the tabs float, a pill
  on the page's background, as they did above the lists. The name stands alone, without
  the category (the lists' count names it). The bar keeps to one line down to about
  950 px, the day of the update going under 1,120 (a phone, the tabs on a line of their
  own, keeps it). The tabs: Papers, Graph, Highly cited, Rankings, Reading list, About.
- Each tab has an icon (`icons.tsx`, UX-31): pages for Papers, the graph's nodes, a
  rising line for Highly cited (the graph's highly cited chip has it too), a podium for
  Rankings, the cards' star for the Reading list, a circled i for About. Under 640 px the
  other tabs are their icons alone, so that all fit without scrolling; their labels stay
  for screen readers, and the current tab shows its own.
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
  | `since` | The days since a day, to the latest, which a bookmark keeps following (PROD-13) | `range` | the same |
  | `range` | A preset: `day`, `week`, `month` (`1`, `5`, `20`, `40` and `all`, from old links, open the one that holds as many days) | `week` | the same |
  | `sort` | `relevance`, `newest`, `citations`, `rising`, `stars`, `custom` (the reading list's own order, UX-39) | `relevance` (the reading list's own order there, without search words) | the lists |
  | `view` | `papers`, `cited`, `graph`, `rankings`, `reading-list`, `about` | `papers` | every view |
  | `paper` | An arXiv id: the paper opened (a list) or selected (the graph) | none | the lists, the graph |
  | `year` | Archive years: `2017`, `2019-2021`, `all`; or `last-12-months` (the latest year until the archive keeps them). Years the archive does not hold show others, which the URL then names in place (`correct`, SRCH-20) | the latest year in Highly cited, the recent days elsewhere | Highly cited, the graph, Rankings |
  | `focus` | A graph node id, `institution:mit`: its papers alone | none | the graph (other views drop it) |
  | `rank` | `author`: Rankings ranks authors (SRCH-13); `country`: countries, on a world map (UX-41) | institutions | Rankings |
  | `metric` | `papers` or `citations`: what Rankings ranks by; for countries `per-million` (papers per million people) or `impact` (highly cited papers only) too | citations for highly cited papers, else papers | Rankings |
  | `folder` | A folder of the reading list (`To read`; UX-38), written in its links only: folders are this browser's, and a name it does not have shows every saved paper | every saved paper | the reading list |
  | `#folder=…&papers=…` | The fragment of a folder's link (UX-46): its name and its papers' arXiv ids, kept while the reading list shows it | none | the reading list |
  | `by`, `at` | An author or an institution, as clicked: that name only | none | the lists, Rankings |
  | `author`, `aff` | Typed author or affiliation text: word starts (old links' `by` and `at`) | none | the same |
  | `venue` | A venue (`ECCV 2026`), a family (`ECCV*`) or any (`*`) | none | the lists, Rankings, the graph |
  | `subject` | A subject, primary or cross-listed (`Machine Learning (cs.LG)`; the select shows `cs.LG`) | none | the lists, Rankings |
  | `xl` | `0`: cross-lists hidden; no control offers it since UX-34, links and saved searches still do (its chip clears it) | shown | the lists, Rankings |
  | `code` | `1`: papers that link their code | all | the lists, Rankings |

## Periods and loading (`period.ts`, `data.ts`, `hooks/use-papers.ts`)

- A preset (`?range=`), a custom date range (`?from=&to=`) or the days since a day
  (`?since=`, PROD-13: "since 15 September" as a bookmark, which new days join; the
  calendar offers it for a range that ends on the latest day, "Keep adding new days"), shown
  by `components/PeriodPicker.tsx`. Its calendar works from the keyboard (UX-14): one day
  takes Tab (the one the focus was on, else the period's last), the arrows move a day or a
  week past the days without papers (`stepDay`), into the next month too, Enter picks, and
  a focused day previews the range as the pointer does; its button reads "Period: …"
  ("Papers: …" as the graph's one-line chip, `compact`), and is muted where the highly
  cited papers show instead (`source`: the graph, Rankings). The presets are the latest day, the last week and the
  last month (`day`, `week`, `month`), counted in calendar days to the latest announcement
  day, so that their names say what they hold: a week has five announcement days, fewer
  after a holiday (SRCH-14). Links to the former presets, counted in announcement days,
  open the one that holds as many (`?range=5` a week, `20` and `40` a month, `rangeOf`).
- Every paper of a period is downloaded and indexed in the browser, so a period loads its
  latest days whole within `PAPER_BUDGET` (10,000 papers: a year of cs.CV, 46,000, would
  take 20 s to index and about 480 MB, which crashes phones), and its older days from the
  search shards within `LIGHT_BUDGET` (20,000 more, `lightDays`; PERF-1): records without
  abstract nor comments, 5,857 of which took 0.3 s to index and 29 MB instead of 1.6 s and
  77 MB, so that about seven months are searched by title, authors, affiliations and venue.
  The period picker says over which days abstracts are searched, and what is left out past
  both budgets. A day file that fails is asked for once more, then left out, and so are
  the days of a month whose shard fails: a notice names them, with Retry (`missingDays`,
  `formatMissingDays`; SRCH-10); only a period whose every day file fails is an error. A
  card of a shard's paper loads its day file for its abstract when it is opened, or on
  "Load the abstract" when abstracts are shown (`hooks/use-whole-paper.ts`,
  `loadWholePaper`), and its ☆ saves the whole record once loaded; a reading list keeps the
  day file (`light`) and the code (`code_url`) of a light one, checked as the build writes
  them (SEC-2). The smoke test builds the site with `VITE_PAPER_BUDGET=3`, so that its
  older day comes from a shard. Links to the former "All days" (`?range=all`) open the
  longest preset.
- `index.html` preloads `data/index.json` (`<link rel="preload" as="fetch" crossorigin>`),
  which every view needs before any day file, so it loads with the page rather than after
  the script; `loadIndex` takes that response, since it asks for the same URL with
  `fetch`'s default mode and credentials, which `crossorigin` gives the preload (the smoke
  test checks the single request): keep the two in step (PERF-14).
- Every other data file is asked for with its version (PERF-8): the build writes the
  first ten hex digits of the SHA-256 of each file the site loads (day and archive files,
  `top-recent.json`, `countries.json`, the citation and search shards), as written, into
  the site's `index.json` (`versions`, `tooling/data-versions.ts`), and `dataUrl` asks for
  `<path>?v=<version>`. GitHub Pages lets a browser keep a file ten minutes: without it, a
  deploy could leave a browser with the fresh index and a day file, search shard or
  citation shard of before. A file the deploy changed gets a new address, one it did not
  keeps its own and its cache. The paths stay the store's, which feeds, links and saved
  papers (`light`) name; the index itself is never versioned, being what names the
  versions, and the development server's has none. The smoke test routes data files by
  patterns that allow the version, and checks one is asked for with it.
- `usePapers` cancels the requests of a period left; `data.ts` keeps the files loaded for
  the next periods (as many papers as a period loads), least recently used out first. It
  loads again only for another period (`periodKey`): Back from a filter or a paper to the
  same period, or its preset chosen again, gives a new object for the same days and keeps
  the index (another period is loaded again, from the files kept); a new load lets the
  former index go before the new one is built.
- The *Highly cited* view (`?view=cited&year=`) loads archive years instead of days,
  ranked by citations: one (`year=2017`), a range (`year=2019-2021`) or all of them
  (`year=all`, which stays all as years are added); without `year`, the latest. They are
  chosen as the graph's (`ArchivePicker`, `components/ArchiveYears.tsx`, UX-33): a
  button naming the years and their papers opens the last 12 months, all years, and a
  grid of the years drawn as the calendar's days, each with its papers, where a click picks
  a year and a second one extends it into a range. Past `PAPER_BUDGET` papers (all years
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
  otherwise. `ArchiveRange` is a `YearRange` or `LAST_12_MONTHS`; the years' panel offers
  "Last 12 months" first, beside "All years", in Highly cited as in the graph and Rankings. They show once
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
- **Search shards** (`tooling/search-shards.ts`, `src/search-shards.ts`, PERF-1): the papers
  of the day files by month (`<category>/search/2026-09.json`), as the site gets them (with
  `doi`, venue and `code` merged) but without `abstract` and `comments` (134 bytes a paper
  gzipped instead of 735, about 6 MB for a year), with `code_url` (the code they linked,
  which `codeUrl` reads then) and `light` (the day file that holds the paper whole). A
  period loads them for its days past `PAPER_BUDGET`; each is loaded once for the page and
  never cancelled, apart from the day files kept (a month would push them out).
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
  websites. Links are fine; fonts, scripts, images or `fetch()` from a CDN are not. One
  exception, given its token: Cloudflare Web Analytics' script (below).
- `landingBudget` (`tooling/landing.ts`) prints what `index.html` loads, gzipped ("Landing
  page: 55.4 kB gzipped of 75.0 kB"), and fails the build past `LANDING_BUDGET` (PERF-15):
  a dependency or a module the list does not need, imported eagerly. Only the whole site's
  size was checked (`deploy.yml`). What the papers' list never shows loads on demand,
  each through `lazyView` (`components/lazy-view.tsx`: its chunk asked for once, a notice
  meanwhile, Reload when it fails): the graph (PERF-13), the world map, and since
  2026-10-17 About, Rankings' tables with the graph's model they rank (`rankings.ts`,
  `graph.ts`; its controls, `RankingsControls.tsx`, stay in the header), the reading
  list's folders and the notice of a shared one, both quiet while they load. The landing
  page went from 72.7 kB to 67.2.
- `contentSecurityPolicy` adds a Content-Security-Policy meta to `index.html`, right
  after its charset (GitHub Pages sends no headers): the site's own scripts, styles, data,
  images and graph worker only (the emoji favicon's `data:` image went with UX-48)
  (`tooling/content-security-policy.ts`, SEC-1). The site renders third-party text and
  links, which it keeps from ever running a script; there is no inline script
  (`public/theme.js` restores the theme), and styles set from code go through the CSSOM,
  which the policy allows, where a `style` attribute written as HTML is refused. The smoke
  test checks that nothing the site does is refused. The development server goes without.
- **Visits** (UX-47, `tooling/web-analytics.ts`): counted by Cloudflare Web Analytics when
  the build is given its site token, `PREPRINT_RADAR_ANALYTICS_TOKEN`, a repository
  variable (Settings, Secrets and variables, Actions, Variables), which `deploy.yml`
  passes: it is no secret, every page shows it. The build then ends `index.html` with
  Cloudflare's snippet (`beaconTag`), and the policy allows its script and the address it
  reports to, those two only (`contentSecurityPolicy(true)`); without it, nothing changes.
  No cookie, nothing stored in the browser; its script reports each page's address
  without the query or the fragment (the search, a shared folder: its code and its reports
  read on 2026-10-16), the referrer, and what the browser says of itself, and Cloudflare
  adds the country, as counts in its dashboard (Analytics & Logs, Web Analytics). About
  says so when the page holds the script (`script[data-cf-beacon]`), and that the site
  loads nothing from elsewhere otherwise. Ad blockers often stop it: the counts are a
  floor. A malformed token fails the build. To stop counting, delete the variable.
- `base: "./"` keeps the site working under `user.github.io/<repo>/`.
- **The logo** (UX-48, `logo.ts`, `components/Logo.tsx`): the designer's files in `public/`
  (the lockup, the mark, a lockup in each theme's fixed colors for `<img>` uses such as the
  README, `favicon.svg`, which follows the browser's theme, `favicon.ico` for browsers
  without SVG icons, `apple-touch-icon.png`, and `icon-192.png` and `icon-512.png`, which
  `manifest.webmanifest` names). The top bar's logo is the lockup inline, 32 px high, so
  that it takes the text's color and the accent on the dot of the i in either theme
  (`.site-logo`, which an `<img>` would not); a link home, named once by the SVG's
  `aria-label`. Its paths are never redrawn, simplified or optimized (the P is cut out of
  the square by `fill-rule="evenodd"`): `tests/logo.test.ts` compares them with the files,
  which Biome leaves as delivered (`!public/*.svg`). Do not go under 24 px high; below, the
  mark alone. Inline, its paths weigh 2.7 kB gzipped of the landing page's budget.
- **A shared link's card** (UX-49, `tooling/share-card.ts`): the Open Graph tags that
  Slack, WhatsApp, iMessage, X or LinkedIn read, the page's title and description in
  `index.html`, and its image, `public/share.png` (the light lockup centered on the light
  background, 1200 by 630, made from the designer's file with `rsvg-convert` and
  ImageMagick), which the build adds with an absolute address when it knows the site's
  (`PREPRINT_RADAR_SITE_URL`, in `deploy.yml`). Those apps read the page without running
  its script, and the site is one page: every link, a paper's, a search's or a folder's,
  shows that same card. A paper's own would take a page of its own per paper (about
  28,500, 35 MB), not made; a folder's name and papers stay in the fragment, which no
  preview sees.
- **Sharing from a phone** (UX-49, `native-share.ts`): a card's and a folder's Share open
  the system's share sheet (the Web Share API) where the pointer is a finger, its title
  and link given; closed, nothing happens. Elsewhere, and when the sheet fails, the link is
  copied as before.

## In this browser only

- **Reading list** (`reading-list.ts`, `hooks/use-reading-list.ts`): stored and exported as
  `{version: 1, papers}`, the bare array of older lists still read. Every entry goes
  through `toPaper`, so that a bad one is skipped instead of breaking the page, and its
  arXiv and PDF links are made from its arXiv id, its HTML link kept only on arxiv.org
  (SEC-2); import
  merges by id; the list follows other tabs through `storage` events and takes the fresher
  record of a loaded day; a refused save is said, not swallowed.
- **Folders** (`folders.ts`, `hooks/use-folders.ts`, `components/Folders.tsx`, UX-38): the
  reading list's papers grouped under names, stored apart from them
  (`preprint-radar:reading-folders`, as `[{name, papers: [arXiv ids]}]`), as the saved
  searches are, and exported in the same file (`folders`; the version stays 1, older files
  have none). A paper is in as many folders as one likes (UX-45, `addPaper`,
  `removePaper`; one at most until then, which the stored form never required: no
  migration). Names are trimmed, cut to 60 characters and kept once whatever their case; a
  file's folders go through `readFolders` (ids kept once a folder when they are arXiv ids)
  and merge by name, a folder taking the file's papers it lacks, which stay in their other
  folders here: nothing conflicts. A folder exports
  alone (UX-44, its Export beside Rename and Delete, `folderFile`): a library file of its
  saved papers and the folder, without the saved searches (`reading-list-to-read.json`),
  which Import library reads as any: the way to import one folder, or to give one to
  someone. The sidebar lists them where the other lists
  choose their period (the reading list had a period picker it did not use): every saved
  paper, then each folder and its count, the one shown (`?folder=`) raised, renamed in
  place or deleted after an inline confirmation (its papers stay saved), and a new one
  named in place. A card of the reading list puts its paper in folders by its menu, once
  there are some (`FolderMenu`: a badge naming its folder, or "2 folders", which opens a
  box to check for each; the card raised over the next while it is open, and a click in
  it does not open the abstract); an unsaved paper leaves its folders (`forgetPaper`), so
  that the counts are the saved papers'.
  The count line names the folder ("1 of 1 saved paper in “To read”"), and the Export menu
  exports its papers.
- **A folder shared by a link** (UX-46, `share.ts`, `hooks/use-shared-folder.ts`,
  `components/SharedNotice.tsx`): the folder's Share (beside Export) copies a link, its
  name and its saved papers' arXiv ids, in the list's order, in the fragment
  (`#folder=To%20read&papers=2610.01234,2609.12345`, commas as they are, 1,000 papers at
  most): browsers do not send it, so the papers shared never reach GitHub's servers, and no
  length limit of theirs applies; a refused clipboard shows the link to copy. Opened, the
  reading list shows the folder in place of the saved papers, a row of its own above All
  saved (another folder chosen leaves it, the row returns to it), with the list's search,
  orders and cards. Its papers are found in the site's data by their ids
  (`data.loadPapersById`): the search shards of the months an id says it was announced in
  (its own and the next, `candidateMonths`; light records, which a card loads whole when
  opened, and which the reading list keeps so), then the archive's years
  (`candidateYears`), then the most cited papers of the last 12 months; one the data does
  not hold (older than a year and not highly cited) is named with its arXiv link. "Add to
  my reading list" saves them, in a folder of that name (merged with one this browser has),
  then shows it; Close drops the link. The fragment is untrusted (`readShare`: a folder's
  name cleaned, arXiv ids only). A paper cross-listed to the category months after its
  submission is in a later month's shard than its id says, and shows as not held unless
  the archive keeps it: rare, and every month's shard would cost about 0.9 MB gzipped each. A copy, not a folder kept in common: that would need a
  server.
- **The reading list's own order** (UX-39): "My order", its default without search words
  (`viewModel().custom`, `?sort=custom`), the stored list's order, the paper saved last
  first, as the user arranges it: a card is dragged by its handle (`.paper__grip`, which
  makes it `draggable` while pressed, so that a drag on its text still selects it) and
  goes before or after the card under the pointer's half, a line in the gap saying where
  (`PaperList`, `movePaper`); Alt+↑ and Alt+↓ move the focused card past its neighbour,
  which keeps the focus. A folder takes a card dropped on it, in any order
  (`PAPER_DRAG_TYPE`), its count bouncing: the paper goes in it too, leaving no other
  (UX-45); All saved takes one out of the folder shown. The handle shows where there is a
  pointer to drag with (`hover: hover`); a phone has the folder menu and nothing to
  reorder by.
  With a search or a folder, a move places the paper by the neighbours shown.
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
  `public/theme.js` before first paint), which `tests/styles.test.ts` checks (UX-18).

## Withdrawn papers, old ones announced lately, and dates by month

A paper whose comments say its authors (or arXiv) withdrew it carries `withdrawn`: its
card shows a Withdrawn badge, the reason being in its comments, and the pipeline keeps it
out of Highly cited (decision 18). Reading lists keep the flag.

A paper announced 12 months or more after the month of its identifier, an old paper
cross-listed lately, says "first version 2019" beside its day (`firstVersionYear` in
`format.ts`, PROD-14); an old-style identifier ("cs/0601001") is not read.

A paper announced before the oldest day file shows its month alone, "Mar 2021", in its
card and the graph's details, with a tooltip saying why (`formatAnnounced`, META-5): it
comes from arXiv's catalog (the archive, the most cited of the last 12 months no day file
holds), which dates it by its first version or the 1st of its identifier's month, not by
its announcement, and arXivRaw, which would give the day, is not harvested. The oldest day
file is the index's, as for the citation shards; once pruning deletes day files (from
September 2027), the archived papers that came from them are dated by month too, losing a
day that was right. The order by newest and the exports keep the stored date.

## Exports and corrections

- `export.ts` writes the results shown as CSV, RIS or Markdown, beside `bibtex.ts` (keys
  with a/b/c on collisions, LaTeX escaping, case-protected words): the Export menu of the
  Papers, Highly cited and reading list views (`papers.bib`, `reading-list.bib`…). They
  cite the published DOI when known, else arXiv's; like the other views, the reading list
  exports the papers its search and filters show. Beside it, the reading list's Import
  library and Export library carry the whole list, its folders and saved searches, to
  another browser (a JSON file; named so since UX-39, the Export menu exporting too).
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
  (`nodeConnections`, `linkPapers`), `GraphLegend` what is drawn, `GraphFilters` which
  papers, `GraphSettingsPanel` how they are drawn (DEBT-3), `GraphFind` the field that
  finds a node, `GraphInfo` the notes on the data and `GraphTimeline` the time-lapse.
- The view's controls (UX-29): which papers and how to draw them apart, since the first are
  the URL's, shared with the other views, and the second preferences of this browser.
  Everything floats on the canvas. At the top left, chips name the papers shown and choose
  them: the period chip ("Last week · 982 papers", `PeriodPicker`, `compact`) opens the
  presets and the calendar, the highly cited chip (`ArchivePicker`) the archive's years (a day or a preset
  goes back to the recent days, a year leaves them: the source that does not show is
  muted), the venue chip is the venue select, and a quoted chip names the words filtering
  the papers, and clears them. The Find field sits under the
  chips (`/`), the details of the node selected below (`.graph__side`; on a phone, the
  field and the chips take a row each and the details are a bottom sheet); the last row of
  its matches, "Only show papers matching…", filters the papers to the words typed instead
  of highlighting nodes. The panel at the top right (`GraphSettingsPanel`) holds
  Nodes (each layer with the legend's color and its threshold, "≥ 2 papers"; isolated
  nodes; Limit), Appearance (Size by; node size; Labels, which reads `labelThreshold`
  backwards: more labels to the right) and Layout, folded, with the forces and Reheat;
  Reset in its head, the exports at its foot. The panel stops above the zoom buttons, and
  folded it is its button alone. The ⓘ beside the legend opens the notes on the data on
  demand (`GraphInfo`): the share of the papers shown whose affiliations are known, with
  the caveat below half, as Rankings has (`affiliationCoverage`, PROD-16), the attribution
  and the citation counts' date (REL-10). The time-lapse is a player at the bottom of the
  canvas, absent for a single day; the mouse hint shows from 1,280 px wide, where it leaves
  the time-lapse room.
- `graph-layout.ts` gives starting positions (each connected component in one piece, on a
  spiral); `graph-renderer.ts` draws on a canvas and handles the pointer (an imperative
  class); `components/GraphView.tsx` and the components above are the UI. It is full
  screen, without the search bar and sidebar, and shows every node unless the user sets a
  limit. The view, its renderer and panels are a chunk of their own, downloaded when the
  Graph tab first opens (`components/LazyGraphView.tsx`, PERF-13: 12 kB of the 61 kB the
  list loaded); a chunk that fails, the site updated meanwhile, offers Reload.
- The force layout runs off the main thread (PERF-2): `graph-simulation.ts` is d3-force
  without a DOM (tested in Node), `graph-worker.ts` ticks it in a module worker and posts
  positions as a transferred `Float32Array` at most once a frame, numbered by graph so
  that late positions of a former graph are ignored. The page draws the latest ones and
  stays responsive: turning authors on for five days blocks it once, about 60 ms to build
  the graph, where the layout on the main thread froze it for seconds. A dragged node
  follows the pointer at once and is pinned in the worker. Under reduced motion the worker
  runs the layout to rest at once, for a new graph, new forces or Reheat. The canvas says
  `data-layout="moving"` or `"settled"`, which the smoke test waits for.
- The layout reaches its equilibrium without Reheat (UX-30): a new graph (or one mostly
  new, the renderer's alpha 1) cools without collisions and with little friction
  (`velocityDecay` 0.1), in 530 ticks up to 2,500 nodes and fewer above, in proportion
  (`coolingDecay`, at least 80), then a last pass with collisions (alpha 0.1) parts
  overlapping nodes. Measured on a week of cs.CV, each two linked nodes' distance against
  two nodes' at random, over three starting positions: the former cooling (300 ticks with
  collisions, friction 0.4) left 0.188, which three Reheats brought to 0.152 in 11 s; this
  one gets 0.153 in 3.6 s (friction 0.2 left 0.164, two Reheats short of it). With authors
  (2,337 nodes, the former fast cooling of large graphs: 82 ticks, friction 0.6) 0.323
  became 0.170; a month with authors (10,234 nodes) 0.383 became 0.226. A layout at its
  equilibrium that moves again settles back with d3's decay and friction (`SETTLING`):
  Reheat (from alpha 0.5), new forces, a graph mostly laid out already (alpha 0.4). Reheat
  from 1 with the cooling's friction moved nodes by a third of the graph's radius; now by
  4%, five times slower. A dragged node of a layout at rest moves as the last pass does,
  and settles quickly. The start of a cooling is not shown (`Layout.hidden`, down to alpha
  0.3, 0.5 s on a week): the starting spiral bursts open there, a frame moving nodes by a
  third of the final radius and the view zooming out 1.6 times to follow; the worker ticks
  without posting, the canvas keeps its former frame, then fades the opened graph in
  (`graph__canvas--reveal`), whose frames move nodes by 1.8% of the radius at most (the
  former cooling, shown from its start: 22%). Equilibrium makes positions mean something, not the default view
  readable: papers and institutions stay a tangle around the biggest institutions, linked
  to everything, where the institutions alone (Papers off) are a map of who works with
  whom (39% of each node's nearest nodes are its neighbors, 16% with papers).
- Touch and keyboards (UX-2, decision 14): two fingers pinch to zoom (`pinchView`, about
  their midpoint, a second finger turning a drag into a pinch), and +, − and Fit buttons
  sit on the canvas. The Find field is a combobox: its first 10 matches are listed
  under it (arrows and Enter choose one, whose details then take the focus), and Enter or
  Shift+Enter go through all the matches, which a status line counts ("3 of 500 matches:
  MIT"). The canvas's label counts its nodes and links, and its description points to
  Rankings, the same institutions and authors as a table.
- Limit (`maxNodes`, "Top 100") keeps the most frequent institutions and authors,
  never papers, and the legend says how many it leaves out (`Graph.eligible`, UX-20),
  naming only the kinds drawn ("top 100 of 750 institutions" without authors).
- Turning authors on hides authors of a single paper (`authorLayer`, the Authors layer's
  threshold at "≥ 2 papers"): they are most of the nodes. The time-lapse stops at every day, or at
  the last day of each week or month when there are more than 60 (`replaySteps`): an
  archive year has about 340 days.
- Sizes: a month of papers (3,500) with all three layers is about 23,000 nodes and 34,000
  links (10,000 with authors of two papers or more); the projection with authors about
  19,000 nodes and 100,000 links (every co-author pair, up to 50 authors); papers and institutions (the
  default) about 5,700 nodes and 6,700 links. The renderer batches drawing into a few
  `Path2D` per frame; graphs over 2,000 nodes use `theta` 1.2, no collisions and a shorter
  cooling (UX-30; about 100 ms a tick for 26,000 nodes, in the worker).
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
  youngest archive years (16% of 2025): the ⓘ beside the count gives their share
  (`format.affiliationCoverage`, "Affiliations known for 331 of 2,018 papers (16%)"), and
  below half the table's own note says it too, with that the others count for no
  institution (PROD-16). What it ranks and by what are in the list's header (UX-33), its
  papers chosen in the sidebar as the graph's: the period, or the highly cited years. A
  column's header ranks the table by it, as the By control does (`SortHeader`, UX-42), the
  column ranked by marked with an arrow and `aria-sort`.
- The world map (UX-41, `world.ts`, `components/WorldMap.tsx`): Rankings' countries
  (`?rank=country`), chosen in the Rank control, and downloaded then (`LazyWorldMap`: the
  map, d3-geo and topojson-client, 49 kB gzipped,
  which the lists never load). A paper is in the countries of its institutions with a ROR
  id (`countries.json`, UX-40), counted fractionally: half for each of two countries, its
  citations shared alike, so that a collaboration is not counted twice. Four metrics: papers,
  citations, papers per million people (countries of a million people or more), and impact,
  the citations per paper over those of every paper placed (countries of 10 papers or more,
  offered for highly cited papers only, recent ones having few citations): the bias of size
  answered twice, by people and by citations per paper. The shapes are Natural Earth's
  1:110m countries in the Equal Earth projection, which keeps their areas
  (`src/geo/world.json`, written by `tooling/world-map.ts` from Natural Earth's files, with
  the instructions there); countries too small for them (Hong Kong, Singapore, Macao: 8% of
  the papers placed) are dots at their 1:50m label points, and each country's name and
  population (Natural Earth's, mostly 2019) come from the 1:50m file, a country's most
  populous entry for its code. Colors by class (`--map-s0`…`--map-s5`, a blue ramp light to
  dark, flipped in the dark theme; `--map-d0`…`--map-d4`, red and blue around a gray for
  impact; hatching where the metric says nothing), the classes of the volume metrics
  spaced on a logarithmic scale at nice numbers (`logThresholds`), as a few countries hold
  most papers. The pointer's tooltip gives the values first, then the country and its
  institutions with most papers; a click pins it. The table under the map, the map's values
  for the keyboard and screen readers, pins a country from its name, brought into view.
  Flat or a globe (UX-43, `components/MapFrame.tsx`, the geometry in `map-view.ts`), as
  this browser last chose (`loadMapGlobe`): the flat map zooms (eight times at most, kept
  to its edges) as a `transform` on its group, the strokes and hatching as thin zoomed;
  the globe (`geoOrthographic`) turns by a drag, opens turning to the first country of the
  metric, and turns to a country pinned from the table (at once with reduced motion); it is
  projected again at most once a frame, 11 ms in development for its 176 shapes. Both
  zoom by the buttons, a pinch, or the wheel with Ctrl or ⌘, a trackpad's pinch coming as
  one (`wheelFactor`, d3-zoom's steps): the wheel alone scrolls the page, the map being part
  of it, and says the key a moment. A finger scrolls the page too (`touch-action: pan-y`),
  but on a zoomed map, which it moves. A tooltip points at the center of a country's
  largest part (`anchorOf`), France's not in the Atlantic. On a phone the globe is drawn in
  a square, the flat map's height too little for it, and the countries' headers wrap.
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
