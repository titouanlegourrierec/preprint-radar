# Changelog

One minor release per phase of [`docs/roadmap.md`](docs/roadmap.md), and one per set of
features in Phase 4, which has no end; a patch for a fix in between. Item IDs (`DATA-2`,
`CIT-11`…) refer to the audit of 2026-09-30
([`docs/audit/2026-09-30.md`](docs/audit/2026-09-30.md)), or, for items found since
(`PROD-17`, `UX-24`…), to [`docs/roadmap.md`](docs/roadmap.md).

## Unreleased

### Interface

- A card says where its citations put a paper among those of its year: "Top 1% of 2017",
  5% or 10%, against every cs.CV paper first submitted that year, from the archive of
  2026-10-25 on (PROD-19).
- A card's More sits against the right edge of its row of actions, in the same place on
  every card whatever badges come before it (UX-50).

### Fixes

- A list of mailbox names in capitals ("{Jane.Doe, A.Roe,") is a contact detail too, and
  no longer an affiliation: on 2026-10-20, one paper's made the data fail validation, and
  neither run of the day stored its 346 papers. The cleaning now drops any string that
  still holds a contact detail, as `validate` sees one, so that an unforeseen page loses
  an affiliation rather than a day of papers (AFF-32).
- The daily re-extraction has 17 minutes for its 50 pages (12.5 at arXiv's pace) instead
  of 12, which ended every run one page short with an `Out of time` warning (CI-16).

### Data

- Highly cited keeps each year's most cited tenth, on top of its rule of citations per year
  of age, which kept 8 papers of 2010 and fewer every year: the years 2010 to 2013 get 138
  papers more, each cited 86 times or more. The weekly archive also writes how each
  complete year's papers rank (`cohorts.json`), for the site (CIT-16, decision 22).
- A day file's paper the archive's catalog does not list (a cross-list first seen before
  2010) competes for the archive on its day, rather than being deleted unranked when
  pruning reaches that day, from September 2027 (CIT-14).
- Extraction version 12: a run of markers before a thanks note's text marks it for each
  of them, as in "*†‡ Y. Yang and J. Bos are with the Department of ...": version 11
  placed only the last of the two authors there, where version 9 placed both (AFF-33).
- The archive's catalog drops the papers arXiv deleted, and every 90 days harvests the
  whole category again, so that a paper no longer listed in it (a cross-list removed)
  leaves the catalog and the archive. The OAI set of a physics category is named as arXiv
  names it (`physics:astro-ph:CO`), for a category added later (META-6).

### Graph

- The graph no longer lays itself out again a moment after it settled, when the citation
  counts arrive: they only change what its nodes say, and their size when citations size
  them (PERF-7).

## 0.10.0 (2026-10-18): Rising stars, OR in the search, and more affiliations read

The fifth set of features of Phase 4: Rising stars ranks the papers by the stars their
code gained in the week; the search takes an uppercase `OR`; the first page loads less,
and a deploy no longer leaves a browser mixing old and new data files; and two extraction
versions read the affiliations a thanks note lists, as IEEE conference papers write them,
and no longer take a sentence about the work for one.

### Code

- Rising stars (`?sort=rising-stars`) ranks the papers by the GitHub stars their code
  gained in the week, then by its stars, in the Papers, Highly cited and reading list
  views, once a second weekly refresh gave gains (the first, on 2026-10-18, gave 1,875). A
  shared repository ranks with the papers that gained none, as in Most starred (PROD-18).

### Fixes

- After a deploy, a browser no longer mixes the fresh index with a day file, a search
  shard or a citation shard it kept from before: the build writes each data file's version
  into the site's index, and the site asks for the file with it, so that a changed file
  has a new address and an unchanged one stays in the cache (PERF-8).
- A refusal of Semantic Scholar that says how long to wait (`Retry-After`) is waited for as
  it asks, rather than by the wait doubling from 2 s, and the run's summary counts such
  refusals, so that the next runs tell whether it sends any (CIT-8).
- When both Sunday runs of *Archive* fail, Saturday catches up while the counts they
  fetched are still cached, instead of the next Sunday asking for all 207,000 again; it
  stops at once after a successful Sunday (CI-8).

### Performance

- The first page loads 8% less: About, Rankings' tables, the reading list's folders and
  the notice of a shared folder download when first shown, as the graph and the map do
  (67.2 kB gzipped instead of 72.7, of a budget of 75).

### Search

- An uppercase `OR` finds either side: `nerf OR "gaussian splatting"`, where a lowercase
  "or" is still a word to ignore. `OR` joins the word or phrase on each side, so that
  `video nerf OR gan` is video, and nerf or gan; the search field's ⓘ says so (SRCH-6).

### Interface

- Text follows the reader's own font size, and none is smaller than 11 px; the controls
  that stand alone (chips, the ⓘ, sortable headers, the graph settings' sliders and
  sections) take a pointer over 24 px at least (UX-16).
- Dates and numbers are written in British English whatever the reader's locale, as the
  rest of the interface is English: "25 Sept 2026" and "10,000", not "25 sept. 2026" and
  "10 000" for a French reader (UX-17).
- One tagline everywhere, the site's description, the card of a shared link, the home
  screen's, the README and the package's: "Follow and search the cs.CV papers announced on
  arXiv every weekday, with their affiliations, citations and the most cited older papers."
  (PROD-15).
- A highly cited paper older than the day files shows its month, "Mar 2021", instead of a
  day: arXiv's catalog, where it comes from, dates it by its first version or the 1st of
  its identifier's month, not by the day it was announced. A tooltip says so, on its card
  and in the graph's details (META-5).

### Data

- The highly cited papers archived before the catalog was cleaned are cleaned each week as
  it is: 7 lose what the author list added to their names ("Jie Qin1", the author
  "others"), and 161 subjects stored by their code are named ("Machine Learning
  (cs.LG)") (AFF-21, META-8).
- An affiliation that writes a longer name holding the one ROR chose gets that one:
  "Texas A&M University-Kingsville" was Texas A&M University, ROR writing Texas A&M
  University – Kingsville with a spaced en dash. Asked again, the 11 stored strings where a
  dash followed the chosen name changed 4 papers (AFF-30).
- Extraction version 10 reads, last, the affiliations a thanks note lists without a
  sentence around them, as IEEE conference classes write them: the whole note
  ("Department of Computer Science, University of Freiburg, Germany."), a numbered one
  each, or a numbered list after other sentences, markers LaTeXML left as text
  (`$ˆ1$University of Southern California`). Of the six IROS papers of the day files
  without affiliations, two have them now; three have none on their page. BMVC's papers,
  92% without affiliations on 2026-10-11, have them since version 8, but one without a
  page; two of their pages and two of IROS's are fixtures now (AFF-11).
- A paper whose page gave no affiliation is asked of OpenAlex a month after it was read,
  then every 30 days while under two years old, as those without a page were: OpenAlex
  learns recent papers over months, and their published versions. One it knows nothing of
  keeps its page's extraction version, so that the next version reads the page again
  (AFF-31).
- Extraction version 11: an "is at" or "is with" of a thanks note gives an affiliation
  only when what follows is a name ("This work is at the intersection of vision and
  language" gave one, which every author then held), cut at its semicolons; one
  affiliation such sentences give places only whom they name; and the numbered markers of
  thanks notes place the authors that carry them (AFF-9).

### Documentation

- Every public function of two parameters or more says what each is (an Args section: 38
  of them had none), and CLAUDE.md lists the commit scopes (DOC-13).
- The README is shorter: what the site does in six lines, where the data comes from, how
  to run and deploy it, the live site's address, and why `data/` is in git, which the
  roadmap's Decisions table logs with the other choices, there being no other record of
  decisions (DOC-2, DOC-3). `docs/archive.md` keeps the calibration of September 2026 that
  chose the archive's rule and budget, its scripts staying local (DOC-4).

### Command line

- Every command declares `-c` and `--data-dir` through one function, each keeping its
  default category: 165 lines fewer in `cli.py`, the same help (DEBT-5).
- `fetch` is gone, with its modules `store/export.py` and `store/filters.py`: it exported
  the raw listing, without abstracts or affiliations, and no workflow ran it; `data/` and
  the site's exports (BibTeX, CSV, RIS, Markdown, JSON) hold more (DEBT-6).

### Security

- `SECURITY.md` says how to report a vulnerability: to the site's correction contact,
  rather than in public, and what counts (SEC-8).

## 0.9.0 (2026-10-17): a new interface, folders shared by a link, and a world map

The fourth set of features of Phase 4: the lists and the graph share one interface of
cards and floating controls, under the site's logo; the reading list has folders, which a
link shares; Rankings has a world map of where the papers come from, flat or as a globe;
and the search ranks first the papers holding its words side by side.

### Search

- Papers holding the search words side by side, as typed, rank first: each two words that
  follow each other, with the stop words between them ("text to image", "image
  generation"), triple a paper's score when all are there, so that "text-to-image
  generation" in an abstract ranks before the three words apart, though not before them in
  a title. The top 20 results of 17 queries of two words or more held them as typed 84%
  of the time, 95% now ("3d reconstruction": 10 of 20, then 20) (SRCH-18).
- Rankings keeps what it ranks and by what in the link (`?rank=author`,
  `?metric=citations`), and its table has a caption and row headers for screen readers
  (SRCH-13).
- The period's calendar works from the keyboard: Tab reaches one day, the arrows move a
  day or a week past the days without papers, Enter picks, and the range being picked
  previews as the pointer shows it (UX-14).
- `?since=2026-09-15` opens the days since a day to the latest one, a bookmark new days
  join; the period picker names it ("Since 15 Sept 2026") and offers it for a range that
  ends on the latest day, "Keep adding new days" (PROD-13).

### Graph

- The graph's controls are split in two, everything floating on the canvas. Chips at the
  top left name the papers shown and choose them: the period chip ("Last week · 982
  papers") opens the presets and the calendar, the highly cited chip the archive's years,
  the venue chip the venues, and a quoted chip names the words filtering the papers, and
  clears them. Find a node sits under the chips: it highlights the matching nodes, and the
  last row of its matches filters the papers to the words instead. The settings panel says
  what is drawn: the nodes, each layer with its color and its threshold ("≥ 2 papers"),
  their size and labels, and the forces folded under Layout. The time-lapse is a player at
  the bottom of the canvas, and an ⓘ beside the legend opens the notes on the data on
  demand: the affiliation coverage, the attribution and the citation counts' date. The
  open panel no longer covers the zoom buttons, and the mouse hint shows from 1,280 px
  wide, where it leaves room for the time-lapse (UX-29).
- The graph's layout reaches its equilibrium by itself: it stopped short of it, and each
  Reheat made the links shorter, by 19% after three on a week of papers. It now cools
  without collisions and with less friction, then parts overlapping nodes in a short last
  pass: as good as three Reheats in 3.6 s instead of 11, and with authors, links half as
  long as before. Reheat is gentler: the layout settles back instead of scattering, and a
  new graph no longer bursts open on screen: it opens out of sight for half a second, then
  fades in and settles gently (UX-30).

### Interface

- The tabs have icons, and on a phone the other tabs are their icons alone, so that all
  six fit without scrolling (UX-31).
- Every view has the same top bar: one line across the window, the site's name on the
  left and the tabs floating on the right, in the same place from one view to the next,
  where the lists had two lines in their column and the graph a ruled bar. The name stands
  without the category, and the Graph tab comes second, after Papers (UX-32).
- The lists look as the graph. Their sidebar holds the graph's chips in a column: Rankings
  chooses its papers with the period and highly cited buttons instead of its "From"
  select, and Highly cited its years with the same highly cited button instead of two
  selects: its panel, in the graph too, picks a year or a range of years on a grid drawn
  as the calendar, each year with its papers. The filters have their icon inside and the
  same chevron as every select. What a view says of its papers is behind an ⓘ beside its
  count, as in the graph: what it shows, how its papers are chosen, how many have known
  affiliations and the citation counts' date; the search's syntax and the keys are behind
  the ⓘ of the search field, which has the graph's magnifier and `/`. Rankings' controls
  sit in the header, where the lists have their order. Fields, buttons and notices share
  the graph's rounder corners, and the cards' star and the theme button are drawn icons
  (UX-33).
- Each paper is a card, rounder than the fields, with a squircle's smooth corners where the
  browser draws them, and so is Rankings' table. A card rises a little under the pointer,
  and a click on it opens its abstract, as More does. "Hide cross-lists" leaves the filters;
  a link or saved search that hides them still does, its chip above the papers clearing
  it (UX-34).
- The sidebar folds, so that the papers take the whole width: the button at the left of
  the count hides it and shows it again, counting the filters set while it is folded, and
  the page remembers the choice (UX-35).
- Highly cited numbers its papers in the order shown, the first three in gold, silver and
  bronze. The export and import buttons have icons, and the last characters standing for
  icons are drawn ones: the code's stars and likes, Seen's check mark and the day
  headings' fold (UX-36).
- Saving a paper bursts its star into sparks, and the star flies to the Reading list tab,
  which bounces as it lands, when the tab is in sight; nothing moves for those who ask
  their system for less motion (UX-37).
- The reading list has folders: made, renamed and deleted in its sidebar, each with its
  count, a paper put in one from its card. They stay in this browser, go into the JSON
  export with the papers, and merge by name on import (UX-38).
- The reading list keeps the order you give it, "My order": drag a card by its handle
  between two others, or onto a folder to file it; Alt+↑ and Alt+↓ move the focused one.
  Its Import and Export JSON are now Import library and Export library (UX-39).
- Rankings has a world map of where the papers come from, its Countries: the countries of
  their institutions, colored by papers, citations, papers per million people, or impact
  for highly cited papers (citations per paper over the world's), so that large countries
  do not hide the others. A paper of several countries counts a share for each; a tooltip
  gives each country's values and institutions, and a table lists them all. The map loads
  only when opened (UX-41).
- A click on a column's header ranks Rankings' tables by it, as the By control does
  (UX-42).
- The world map zooms, with its buttons, a pinch, or the wheel holding Ctrl or ⌘, and a
  drag moves it; it turns into a globe, which a drag turns, and which turns to a country
  chosen in the table. The page remembers Flat or Globe (UX-43).
- A folder of the reading list exports alone, from its Export beside Rename and Delete: a
  file of its papers that Import library reads, the way to bring one folder to another
  browser or to give it to someone. The folder merges by name (UX-44).
- A paper can be in several folders: its card's menu has a box to check for each. A card
  dropped on a folder goes in it too, and on All saved leaves the folder shown; an import
  adds a folder's papers to the folder of that name, whatever other folders hold them here
  (UX-45).
- A folder is shared by a link: its Share copies it, and whoever opens it sees the
  folder's papers in their reading list, with a button to add them, in a folder of that
  name. The link names the papers after a `#`, which browsers never send to the server
  (UX-46).
- Visits can be counted by Cloudflare Web Analytics, without cookies: given its site token
  as a repository variable, the build adds Cloudflare's script, the only thing the site
  then loads from elsewhere, and About says what it counts; without it, nothing changes
  (UX-47).
- The site has its logo: a P cut out of a rounded square beside its name, in the top bar
  (a link home), in the theme's colors, and as the tab's icon in light and dark, the
  phone's home screen icon, and the README's heading (UX-48).
- A link to the site shared in a chat or a post shows a card with the logo, its name and
  what it does. On a phone, Share opens the system's share sheet (Messages, WhatsApp,
  Mail…); on a computer it copies the link, as before (UX-49).

### Data

- The institutions of the stored papers are placed in their country, from OpenAlex, by
  their ROR ids (`countries.json`, `make countries`, in both data workflows): 85% of the
  papers have a country, in 108 countries, for the coming map of where they come from
  (UX-40).

### Performance

- The page loads 18% less script: the graph, its renderer and panels download when the
  Graph tab first opens (49.9 kB gzipped instead of 60.8). The build prints what the
  landing page loads and fails past 75 kB gzipped (PERF-13, PERF-15).
- ROR is asked only for affiliation strings it never answered: the 7,343 it named in the
  day files are reused (AFF-17).

### Fixes

- A day file that fails to load no longer fails its period: it is asked for once more,
  then left out with a notice naming the days missing, those of a month whose search shard
  failed too, and Retry. A period whose every day file fails is still an error (SRCH-10).
- A page that sets its list of acronyms before its title is kept whole in the page cache:
  it was kept empty, and two papers read again from it lost their affiliations, which are
  back. A paper read again from a page kept with less than its front matter keeps what it
  had while the page is downloaded again (DATA-1).
- "UCSD" written alone is the University of California San Diego as ROR writes it, without
  the comma that made it an institution of its own; `validate` warns of an acronym's
  institution that no institution with an id is called (TEST-9).
- A day arXiv announced late is no longer missed when its cache serves the recent listing
  hours old, as on 2026-10-15: the listing is asked for without the cache, and a weekday
  it still lacks comes from that day's catchup page, with a warning `Listing out of date`
  (REL-12).
- `update` catches up by itself after an outage longer than the five days the listing
  holds, or when papers are still pending on a day the listing dropped: it reads every day
  since from the catchup pages, within 30 days, with a warning `Catching up` (CI-7).
- A link to a year the archive does not hold (`?year=2005`) names the year shown instead,
  in place, so that a shared link opens what was seen (SRCH-20).
- A listing or catchup page whose entries lost their authors (more than 10%), or their
  HTML links (more than half), fails the run instead of storing papers without them: the
  arXiv layout changed (REL-7).
- With several categories, one that fails no longer stops the others: `update`, `backfill`
  and `reextract` run the next ones and exit 1 (REL-5).

### Dependencies

- Preact 11 (from 10), Ruff 0.17 and the week's other updates Dependabot proposed.

### Security

- The site has a Content-Security-Policy: its own scripts, styles, images, data and graph
  worker only, so that the third-party text and links it renders can never run a script. The theme is restored before first paint by a file rather than
  an inline script (SEC-1).

## 0.8.0 (2026-10-15): months of search, and five more page layouts read

The third set of features of Phase 4: a period searches months of papers, its presets are
a day, a week and a month, and the extraction reads affiliations from five more layouts of
arXiv's pages.

### Search

- A period searches months of titles, authors, affiliations and venues, not only the days
  it loads whole. The build writes the papers of the day files by month without their
  abstract and comments (`<category>/search/<YYYY-MM>.json`, 134 bytes a paper gzipped
  instead of 735); a period loads its latest days whole, within 10,000 papers, and its
  older ones from these, within 20,000 more: about seven months. Without them, a period
  would have loaded only its latest days from about 2026-11-12 (PERF-1).
- Abstracts are searched over the days loaded whole, which the period picker says; the
  card of an older day loads its abstract when opened, or on "Load the abstract", and its
  star saves it whole. A month that fails to load leaves its days out, with a notice and
  Retry.
- The presets are the latest day, the last week and the last month, in calendar days to
  the latest announcement day, where they were 1, 5, 20 and 40 announcement days; the
  calendar picks any other period. Links to the former presets open the one holding as
  many days, and "All days" the month (SRCH-14).

### Data

- Extraction version 8 reads five more layouts: affiliation notes after the abstract
  (Taylor & Francis), numbered lines LaTeXML sets as authors, an affiliation glued to its
  author's name, lines led by symbols, and the lines under the names that name an
  institution or end with a country. Of 100 pages stored without affiliation, 29 give
  some. Markers written in math, an address before a full stop and a glued "Email:" label
  no longer misplace authors (AFF-29).
- Version 9 fixes what version 8 got wrong on the archive's pages: names glued to each
  other read as an affiliation, pieces of author fields cut at commas ("Technology of
  China"), symbols that follow their affiliation, markers after two spaces, and IEEE's
  template author. With it, the cached pages of the highly cited papers gave 79 more of
  them affiliations, none lost; the daily re-extraction reads the 1,993 papers of version 7
  again.
- `archive-affiliations` no longer reads first the cached pages that gave nothing: its
  second run stopped after a second, taking them for a layout change (AFF-28).

### Fixes

- GitHub's limits are waited for: at one query a second, 48 of 79 were refused on
  2026-10-11, and 4,698 papers kept the stars of the week before. One query every 3 s; a
  refused one waits for its `Retry-After`, else a minute, then two, and the run stops
  asking after a third refusal (PROD-18).
- A Semantic Scholar answer that is not one entry per paper asked for is no longer retried
  for 25 minutes as a refusal, leaving the 1,415 papers after it without a count: it is
  asked for in halves down to the paper it cannot answer for, which alone is left out,
  with the answer in the log (CIT-15).

### Continuous integration

- *Update data* restores the archive's catalog on weekdays too, only to keep it in the
  Actions cache: the archive of 2026-10-11 found it evicted and harvested it again
  (CI-10).
- The build backend is `uv_build` 0.13, the uv every run installs, which warned at each
  run.

## 0.7.0 (2026-10-09): the stars of the code, and the last 12 months of Highly cited

The second set of features of Phase 4: the code a paper links and its GitHub stars, the
most cited papers of the last 12 months, the affiliations of the highly cited ones from
their published versions and pages, and cards whose links are badges.

### Code

- A card's links and controls are badges, on a row of their own under its facts, neutral
  rather than blue links, each with an icon: the logo of the site linked for DOI and Code
  (GitHub, GitLab or Hugging Face), drawn ones for PDF, HTML, BibTeX, Share, Graph, Seen
  and More. The stars of the code are the second part of its badge, and the authors and
  the affiliations each follow an icon (UX-28).
- A card shows the GitHub stars of the code it links, "★ 1,234", with those gained in the
  week ("+12 this week"), or the Hugging Face likes of its models, data or demo; a
  repository other papers link too, or a folder of a larger one, is marked shared, its
  stars not the paper's alone (PROD-18).
- Most starred (`?sort=stars`) ranks the papers by those stars, the shared ones with the
  papers without stars, in the Papers and Highly cited views, once the stars are known.
  The sort control takes two rows on a phone rather than cut its labels.
- The stars of new papers come with the next weekday's run (`code --new`, `NEW=1`), not
  the next Sunday: only the papers without them are asked for, the week's gains kept.
- `make code` fetches them into `code.json`: GitHub's GraphQL API, 100 repositories a
  query, a minute for the 7,541 repositories of the stored papers; it needs a GitHub
  token (`GITHUB_TOKEN`, any). The weekly archive runs it with the workflow's own.

### Search

- "With code" keeps the papers that link their code, about one in five: a repository on
  GitHub or GitLab, else models or data on Hugging Face, which their card links (PROD-12).
- A clicked author or affiliation is marked as a whole name, in the author and affiliation
  lines only: filtering on "Hao Li" no longer marks "lightweight" and "linear" in titles
  and abstracts (SRCH-8). Typed, "J.Smith" marks "John Smith", as the filter keeps the
  paper.
- The venue filter has every edition of a venue at once, "CVPR, any year", its workshops
  apart (SRCH-15).
- The subject filter keeps the papers listed under a subject, primary or cross-listed:
  cs.RO holds 478 stored papers, 256 of them primary. Its choices show the code and count
  every loaded paper, so choosing one no longer leaves it alone; old links keep working
  (SRCH-9).
- With search words, Most cited and Rising keep the best match first among equal counts,
  most of a recent day's papers, instead of the newest (CIT-6).
- Names compare alike on the site and in the pipeline: "Nießner" and "Niessner",
  "Bartłomiej" and "Bartlomiej" are one author in the graph and Rankings, and searching
  "lukasz" finds "Łukasz". BibTeX keys write these letters plainly, and the feed of an
  institution that writes them moves ("…-giessen.xml") (AFF-24).
- Text typed in the Author or Affiliation filter searches, and goes into the link, after
  the search box's short pause instead of at every key; a clicked name, the checkboxes,
  the venue, the subject, Back and Forward still apply at once (PERF-4).

### Fixes

- `make venues` no longer takes the prices of an abstract for formulas ("saving nearly
  $300,000" lost its dollar), and a group around a formula loses its braces when the
  abstract is read: "an 8× speedup", not "an {8×} speedup" (SRCH-19).
- A list of mailbox names cut across two nodes of a page, or holding an underscore
  ("{pau.rodriguez,...,michal_klein,", then "Apple"), no longer ends up in an affiliation:
  the first run over the highly cited papers' pages stored one, which `validate` refused
  (AFF-28).
- Back from a filter or a paper to the same period, or its preset chosen again, no longer
  loads and indexes its papers again: the list stays as it was (PERF-16).
- A page that fails to draw says so, with Reload, a link to start over and whom to tell,
  instead of going blank; the tabs and the sidebar stay usable, and Back or another period
  draws it again (TEST-10).
- While a view loads, the header and the graph say what: "Loading 3,646 papers of 5
  days…", "Loading 3,407 highly cited papers of 2024…" (UX-6).
- The store's index loads with the page, preloaded, instead of after the script (PERF-14).
- A backfill goes on past a day whose catchup page fails or lists fewer entries than it
  announces: that day is not saved, the others are read, the report names it and the
  command exits with 1; after three such days in a row it asks for no more. A dated
  `Retry-After` is honoured (REL-4, REL-8).
- A file of citation counts that fails to load is reported in the browser console instead
  of being dropped silently (SRCH-10).

### Triage

- Marking a paper seen (x) while seen papers are hidden, or unsaving it (s) from the
  reading list, keeps the papers loaded below it and gives the focus to the next one; it
  used to fold the list back to 40 papers and lose the keyboard's place. Late citation
  counts no longer fold it either (UX-23).
- "Hide seen" says what it hides: "· 12 seen papers hidden" by the count, and "All 12
  papers here are marked seen" with "Show seen papers" when nothing else is left (UX-26).
  The paper a link opened stays while it is open, seen or not; folded, it leaves and
  hands the focus on.
- The reading list has the Export menu of the other lists (BibTeX, CSV, RIS, Markdown, of
  the saved papers its search shows), beside Import and Export JSON (SRCH-16).
- A list prints as its cards, black on white whatever the theme, none cut by a page
  break, each with its arXiv address under the title, without the controls, sidebar and
  graph; the browser's bar takes the page's background, that of the forced theme too
  (UX-18).

### Highly cited

- Highly cited offers the most cited papers of the last 12 months ("Last 12 months",
  `?year=last-12-months`), in the graph and Rankings too: the store held none from
  October 2025 to August 2026, the archive starting at 12 months and the day files in
  September 2026. The weekly archive keeps the 1,000 best by citations per month of age,
  counted over two months at least, so that each month has its own, in `top-recent.json`;
  those of the day files are their records there, the others come from arXiv's catalog,
  with affiliations from OpenAlex. A paper's link opens it there. The first list comes
  with the archive of 2026-10-11 (PROD-11).
- Highly cited shows a range of years, or all of them, not only one: "2019 to 2021",
  "All years", in the graph and Rankings too. Past 10,000 papers (all years hold 22,000),
  the best ranked for their age are shown, and the page says how many are left out
  (PROD-17). From a graph of archive years, "Show all" and opening a paper go to Highly
  cited over the same years, no longer to an empty list of recent days.
- Highly cited offers Show abstracts, and a card announced a year or more after its first
  version says so ("first version 2019") (PROD-14).

### Data

- Highly cited papers without affiliations get those of their published version from
  OpenAlex, each author placed by name: 6,799 of 10,520 at once, the archive from 53% to
  83% with affiliations, 2025 from 16% to 51% (AFF-20). The weekly archive runs
  `archive-affiliations` after `scholar`.
- `make archive-affiliations MAX_HTML=N` also reads the HTML pages of those still without
  any, about 2,000 of 2024 and 2025, the most cited first: a night at arXiv's crawl delay,
  resumable, its 404s remembered in the page cache (AFF-28). A paper that leaves the last
  12 months for the archive keeps the record it had.
- The papers arXiv has no HTML rendering of, 5% of them, get their affiliations from
  OpenAlex: 94 of 225 at once, and the others are asked for again every month, as OpenAlex
  learns them (AFF-27). The daily workflow runs `affiliations` after the re-extraction.
- A paper of the day files looked up by OpenAlex in the archive no longer keeps the
  version of the HTML extraction that gave its former affiliations (META-9).
- The weekly archive identifies itself to arXiv's OAI-PMH with the contact, as the listing
  and the pages do; Semantic Scholar and OpenAlex still get the bare User-Agent (DOC-8).
- Report and log lines group digits ("1,234 listed"), and `--help` says where abstracts
  come from today, what the archive writes and what `validate` checks (DOC-8).
- The pipeline refuses a store file of another `schema_version`, naming the file and both
  versions, instead of misreading it or relabelling it; a breaking change ships with its
  migration of `data/` (DATA-9, ARCH-7).
- Papers entering the archive name every subject as the listings do, from arXiv's taxonomy
  where the day files never named it, and lose the footnote marks, the leading "and " and
  the "others" that arXiv's metadata leaves among author names (META-8, AFF-21).

### Command line

- In a terminal, the long steps draw a progress bar: what they do, how many items of how
  many, the time spent and the time left (HTML pages, citation counts, published
  versions, OpenAlex, ROR, GitHub stars); log lines print above it. In CI and pipes the
  output stays plain lines (UX-27).
- The long commands (update, backfill, reextract, institutions, citations, scholar,
  archive) log their progress without `-v`, and `-q` keeps warnings only (DOC-5); `-v`
  before and after the command add up.
- `--crawl-delay inf` or past an hour, and a `--match` that is not a regular expression,
  get a usage line instead of a traceback (DEBT-5).
- `update` and `backfill` read at most 600 HTML pages a run by default, which fits the
  daily workflow's time; `--max-html` (`MAX_HTML=` with `make`) changes it. Reading pages
  logs the time it should take, and each checkpoint the time left (DEBT-7, DOC-12).
- `make` leaves the categories to each command, so reports cover every stored category;
  `make archive` takes `DRY_RUN=1`, `BUDGET=N` and `PRUNE=1` (DOC-9).

### Continuous integration

- A running deploy of the site is never cancelled: that left the data run that called it
  without success, so its fallback ran the whole update again (CI-9). A push deploys once
  the web tests pass (CI-4), a burst of pushes is tested once, and the static checks run
  on one Python version (CI-14, TEST-13).
- A fork that turns its Actions on no longer crawls arXiv on schedule: the data
  workflows' guard stops their scheduled runs there, and the canary skips its jobs (CI-11).

### Security

- An imported reading list can no longer put a `javascript:` address on a paper's links:
  they are made from its arXiv id, as the store makes them (SEC-2, SEC-7).
- The site's deploy gives its build, which runs npm packages, no token that could deploy:
  each job gets only what it needs (SEC-3, CI-6). The Semantic Scholar key reaches only
  the steps and the `make` targets that ask Semantic Scholar (SEC-5). Dependabot proposes
  a release once it is 5 days old, 14 for a major; security updates do not wait (SEC-6).

### Accessibility

- A card tells screen readers what a copy did, downloads its BibTeX when the clipboard is
  refused and says so, opens from its "+N" authors or affiliations ("+3 more authors"),
  whose first name shown takes the focus, and its seen toggle is "Seen", pressed or not
  (UX-15).
- Links inside text are underlined everywhere (the footer, About, "Report an error",
  notices, the feed line, the graph's details), not told from the text by their colour
  alone (UX-24).
- Counts read right: "10,000 of 10,000 papers" with the reader's separator, and "1 paper"
  rather than "1 papers", in the list, the graph, the calendar and the filters (UX-25).
- The graph says a failed load as the lists do, an alert with Retry (UX-6).
- The graph settings' search field and selects show the focus ring again, and the search
  box has an outline in high-contrast modes, which drop its shadow ring (UX-9).

### Feeds

- Every institution of the recent papers, and each major venue, has an Atom feed of its
  papers of the last 60 days: filtered on one, the list links it, for a feed reader
  (§17.1 #6). An institution of the Highly cited papers alone, which has no feed, links
  none.

### Graph

- The graph's cap says what it does, "Top institutions & authors", and its legend how
  many it leaves out ("top 100 of 5,993 institutions", authors named only when drawn)
  (UX-20).
- The graph's settings name the sources of its data and the date of the citation counts,
  as the footer does elsewhere (REL-10).
- Each connection of a node lists the papers they share ("what did MIT and Google write
  together"), "Focus on this" shows the graph of a node's papers alone, with a link to
  share it, and the graph saves as PNG or GraphML for Gephi (§17.1 #8).
- Rankings and the graph's settings give the share of papers whose affiliations are known,
  "Affiliations known for 331 of 2,018 papers (16%)", and below half that the others count
  for no institution (PROD-16).
- A name a paper lists twice is one author, placed wherever either occurrence is (AFF-21).

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
