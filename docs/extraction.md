# Affiliations, venues and abstracts: how they are extracted

The rules behind `sources/arxiv_html.py` (affiliations and who is where), `venue.py` (the
venue of a paper), `latex.py` (abstracts as plain text) and their offline re-runs. Every rule here was added for a real page;
the arXiv identifiers are the evidence. Read this before changing the extraction, and do
not "simplify" a rule away without the page that made it.

## Ground rules

- Affiliations come from the submitter-declared ones of the API when present, otherwise
  from heuristics on LaTeXML's HTML front matter. Raw LaTeX sources are **not** an
  alternative: `robots.txt` disallows `/e-print` and `/src` (export.arxiv.org disallows
  everything), and LaTeXML's HTML is already parsed LaTeX.
- Every new heuristic gets a fixture under `tests/fixtures/html/`, with its authors in
  `expected.json` first. After a deliberate change, `UPDATE_GOLDEN=1 uv run pytest
  tests/unit/test_golden_fixtures.py` writes `expected.json` again: its diff is the review.
- Bump `EXTRACTOR_VERSION` with any change to what a page gives (affiliations, mapping):
  nothing else tells `reextract` that stored papers are out of date. A change to the
  cleaning alone (`clean_affiliation`) reaches stored strings through `make reclean`, then
  `make institutions`. Changes that need the page (mapping tiers, new sources) only reach
  papers read again.
- Measure before and after: `make quality-affiliations` (with `--page-cache-dir`, the
  cached pages as stored and as extracted today, nothing written) and `make stats`. Before
  bumping `EXTRACTOR_VERSION`, `make extraction-diff` lists every cached paper the change
  touches, those that would lose words first: read each one. A lost word is an author's
  name or noise, or a regression (2610.02974 lost "Alicante" to the "at" of an address).

## Sources, in order

- `ltx_role_affiliation`/`ltx_role_address` contacts in `div.ltx_authors`.
- `ltx_note` of roles `address` and `institutetext` anywhere, and `footnotetext` notes that
  are direct children of the article and start with a marker.
- Numbered lines after the names.
- "A is with B" sentences in `thanks` notes.

A source that only names authors leaves its turn to the next one: IEEE classes put the
names in the affiliation macro and the affiliations in thanks notes.

Thanks notes keep the line breaks of their LaTeX source, which wrap sentences anywhere
("are with the School of" / "Intelligent Engineering and Automation", 2609.33097): a line
continues the previous one unless that one ends with `.;:!?`, or the line starts a
sentence of the usual notes ("Manuscript", "Corresponding"…), a marker ("* Equal
Contribution") or a new "B is with" statement, though a statement whose list of people
wrapped joins its start ("Bo Zheng, …, Weinan Guan," / "Zhiheng Li, … are with",
2609.15562). Read line by line, 2608.30657 gave "School of Mechanical and" and "School of
Artificial".

## Cleaning

- Several "is with" sentences on one line: each affiliation ends at the last full stop
  before the next sentence, skipping initials ("..., Spain. L. Zhinin is with"), so that
  abbreviations inside it survive ("Dept. of CS, MIT, USA").
- "A and B are with X" gives X wherever it is written, affiliation macros included (unless
  what precedes the verb names an institution). So does a role in an affiliation macro:
  "Manoj Karnekar is Robotics Lead at FloMobility Pvt. Ltd." (2610.05505); not in thanks
  notes, where "is available at" would read as one. IEEE's "X, China, and also with Y" is
  split: `clean_affiliations` returns every affiliation of one string, and the author gets
  them all (2609.00814).
- Author names printed as affiliations ("Nicolás Ugrinovic", "Yiqun Zhang, and Yiu-Ming
  Cheung", "Benoît Macq Fellow, IEEE") are dropped by `names_only_authors`, which compares
  each name of the list by `name_key`. Strings with an institution word stay, and so do
  collectives that sign as authors ("Alzheimer's Disease Neuroimaging Initiative"). Once
  names were dropped, a single affiliation left is not everyone's: 2609.38180 would
  otherwise put Takaaki Shiratori at CMU.
- Obfuscated addresses ("jane (at) example.org", "lab [at] example.org") and lists of
  mailbox names ("{jane.doe, john.roe}") are stripped, keeping the affiliation they follow;
  so is an address in brackets, with what follows it: thanks notes, once unwrapped, end
  their sentence with one ("..., Hong Kong SAR, China (xhubd@...)", 2609.10082), which
  made the whole sentence a contact detail. So is an address that ends a line ("...,
  Vienna, Austria schwaige@...", 2610.02974): its four authors lost their university;
  mailboxes before their domain too ("..., Germany. {pm.wolf, cremers}@tum.de",
  2610.03283).
  `_JUNK_RE` rejects what still passes: lone words ("the", "dot"), link and contribution
  leftovers ("Code", "Core Contributors"), units cut off by a line break ("School of") and
  lone countries. For records extracted before, `institutions.institution_name` names no
  institution for such leftovers, through its own narrower `_JUNK_RE` and its
  `_COUNTRY_RE` (`src/preprint_radar/institutions.py`); the site names none itself
  (AFF-13).
- Superscript markers split affiliations, except one between two lowercase letters
  ("Hyper<sup>2</sup>labs" is a name). Every `<br>` is a line break, also when LaTeXML
  writes no newline after it.
- IEEE classes lose some line breaks altogether ("Dept. of Computer ScienceUniversity of
  Alabama", 2609.00446): `clean_affiliation` puts a comma where a lowercase letter meets a
  capitalized word, or a closing bracket a word, after a unit word of the same part; never
  inside brackets ("(ShenZhen)") nor after a hyphenated word, so that names stay
  ("AnimSchool", "ByteDance", "McGill"). A brand written after a unit in the same part ("AI
  Lab of ByteDance") would be split, which no stored string does. Being cleaning, it
  reaches stored strings through `reclean`.
- A line ending with "," or "and" continues on the next one, and a line that only names a
  place joins the previous line when that one has no country.
- A line starting with "and" goes on with the unit that ends the previous line: "Faculty of
  Medicine" then "and Health Sciences" (2610.03290). Not after an institution ("Stanford
  University" then "and Mila"), nor when "&" starts it ("& Canada-CIFAR AI Chair").
- A line that only names authors is never joined to the next: "Terrence Chen, Ziyan Wu"
  then "United Imaging Intelligence, Boston MA, USA" (2610.02382) are names, dropped, and
  an affiliation, not one string with the names inside.
- A unit without its institution ("Department of Computer Science": a unit word, no
  institution word, no comma; `is_bare_unit`, which the quality sign uses too) takes the
  next line: "Department of Computer Science, Dartmouth College, Hanover, NH, USA"
  (2609.38705, AFF-10). Not when a marker starts that line (two affiliations), when it is
  another unit ("Department of ECE" / "Department of CS" / "University of Central
  Florida" gives the institution to the second only, 2610.02000), nor when it is a note
  ("Corresponding author"), which would make the whole string noise.
- IEEE conference classes write each line of an author's address as its own contact node:
  an author's nodes are read as the lines of one text, by the extraction and the
  per-creator tier alike.
- Numbered markers written as text inside a string ("Cornell University 2University of
  California, Berkeley", AFF-23) split it: one or two digits glued to a capitalized word
  ("2Duke", "3HKUST", "4eBay") after a space, when the word before holds no digit or is
  itself marked ("2CASIA 3HKUST"), so that postcodes stay whole ("London WC1E 6AE", "QC
  H2S 3H1") and so do "3D" or "4K". This is cleaning, so `reclean` splits stored strings.
- Leading digits are markers unless they start a name: "54th Research Institute", "2nd
  Department", "3M Company", "3D Vision Lab" and "4K" keep them, in cleaned strings and in
  numbered lines ("2 3D Vision Lab").
- LaTeXML prints the spacing of a line break (`\\[5pt]`) as text: `[5pt]`, `[0.2em]` are
  line breaks, never affiliations.
- Link labels ("Project page", "Project Website") are stripped, not dropped: once the URL
  is removed as a contact detail, the label is often glued to the affiliation before it
  ("MITProject page"). Anything mentioning correspondence is noise.
- elsarticle's `organization=…, city=…, country=…` text (printed verbatim by LaTeXML)
  ignores line breaks: a repeated key starts the next affiliation, and `clean_affiliation`
  turns the rest into plain values, organization first. Keep that conversion in
  `clean_affiliation` only, since the author mapping looks affiliations up through it.
- Contact nodes are joined within one author's only: an address spread over the creators
  of a table ("Department of Computer Science, University of Alabama at Birmingham" under
  one author, "Birmingham, AL, USA" under the next, 2609.13271) stays apart. A place
  without a country ("Pittsburgh, PA 15213") is not recognized as one: US states are not
  in the list, since their codes are words ("IN", "OR", "ME").
- The countries are those affiliations write (AFF-18), but for those that are also names
  of people (Jordan, Chad, Georgia), which a line of names would end with, and Wales, which
  ends "New South Wales". A name that ends with a country without a comma ("National
  Research Council Canada") takes a place in the same country ("London, ON, Canada",
  2609.12374), not one in another ("University of Luxembourg" then "Trier, Germany", the
  next column of a table, 2609.06629). The institution rules' `_COUNTRY_RE` is built from
  the same `COUNTRIES`, so there is one list; the site keeps only the acronyms of its
  search, which `test_the_site_knows_the_same_acronyms` keeps equal to Python's.
- A line ending with a preposition ("Key Laboratory ... of Ministry of" then "Education,
  Jilin University", 2609.11477) continues on the next one, unless a marker starts it.
  Lowercase only, after a space: "TU Wien, AT" ends with a country code, and
  "schwaige@technikum-wien.at" with the domain of an address (2610.02974), which then
  made both lines one contact detail.
- A list cut after its connector loses it ("The University of Hong Kong, and"), and so does
  a trailing dash; a name cut short keeps its "and" ("Nanjing University of Posts and"),
  which the quality signs show. Phone numbers ("Tel.: +49 ...") and placeholders ("TODO:
  ...") are noise, and a LaTeX command printed as text is dropped ("\\addrDepartment of
  ...", 2610.04051).

## Who is where: the author mapping

The mapping reuses the same nodes, in tiers: per-creator contacts, superscript markers
matched with marker-led (or marker-trailed) lines, "A is with B" sentences (in thanks notes
and affiliation contacts: 2609.06721 writes them in the last author's block), plus the
trivial single-affiliation and single-author cases. A wrong pair is worse than none:
ambiguous name alignments drop the whole tier, and unresolved authors stay `null`.

- Links set as authors ("Project Page", a repository) are not creators: 2609.37107
  followed its last author with two, and its shared block went unnoticed.
- After a name, a marker glued to the next word introduces an affiliation line, not the
  name's: "Bob Smith⟨2⟩ ⟨1⟩Stanford University" places Bob at 2 only. In free-form blocks
  such a marker also starts a numbered line, for the affiliations and their anchors
  alike: "University of California, Berkeley ⟨2⟩Duke University ⟨3⟩Carnegie Mellon
  University" was one affiliation, and nobody was placed (2609.38079).
- Symbols come off a marker's number: "⟨2,6*‡⟩" is 2 and 6, and "∗" (LaTeX's `\ast`) is
  a note like "*" (2609.35052). A run of known markers without separators ("12", "⋆†")
  is read one by one.
- Anchors match affiliations without regard to commas: a marked line read as one text
  ("Department of Computer Science University of Central Florida") is the affiliation its
  lines were joined into (2610.02000).
- Per-creator contacts place nobody when only the last creator carries them: LaTeXML
  attaches a block shared by every author to the last one (2609.37098 gave its 7
  affiliations to its 9th author, 2609.00866 its 25 to its 55th).
- A creator naming several people ("A, B and C", "A & B") is left out of the per-creator
  tier: 2609.05583's single creator for six authors is then placed by its markers. So is a
  creator holding several authors' names without any separator: 2610.01434 writes its
  eight authors apart by wide spaces, and the creator went to the last author, with every
  affiliation.
- A pair ("Zhiyuan Yang & Jiahao Cheng", no comma, no marker on the names) beside other
  creators shares the block under it: both are placed (2609.36407). Alone, or with markers,
  it says no more than a list; nor does a block that only names a place, the end of an
  address the creators before began ("Orlando, FL 32816, USA", 2609.34021).
- A marker's text runs to the next marker, read as one line: it may hold the lines an
  affiliation was joined from, then another affiliation of the same marker
  ("⟨2⟩Laboratory … Response / Technologies (LiGHT) / Swiss Federal Institute of Technology
  (EPFL), …", 2610.03290). When it cleans to no affiliation, it is cut into the paper's
  affiliations, one after another; a text not wholly made of them anchors nothing.

## Institutions (ROR, then `institutions.py`)

`api.ror.org/v2/organizations?affiliation=` marks one match `chosen`. Only those are kept,
and only when one of the organization's names (not an acronym) of at least two words
appears word for word in the affiliation: `chosen` alone matched "ARC Lab, Tencent" to an
association called ARC and "180 Queen's Gate" to "The Gate". ROR names about 70% of the
strings (universities in full), and gives each its id (`institution_ids`). A failing ROR
never fails a run: lookups stop and resume next run.

The rest are named by `institutions.name_institutions` (AFF-13, decision 12), which the
site applied itself until 2026-10-07, in TypeScript; the port gave the same name for all
37,789 stored affiliations. An affiliation is split at commas and its most
institution-like part kept (a university over an organization over anything else; a unit
or an address alone names nothing): "School of Computer Science, Peking University" is
Peking University. A known acronym written alone is its institution as ROR names it
("CMU", `ACRONYMS`, which the site keeps for its search, a test keeping both equal); a
company mentioned anywhere is the company ("ARC Lab, Tencent IEG" is Tencent), but a
hospital named after it is not; a campus of the University of California keeps its city.
ROR's and OpenAlex's names go through `canonical` too, so that a company's subsidiaries
("Google (Switzerland)", "Tencent (China)") are one institution. One of the paper's own
authors is never an institution.

An institution with a ROR id came from ROR (or OpenAlex, in the archive, whose names are
registry names with or without an id); one without, from the rules. `make
institutions-again` names the stored institutions again after a change to the rules:
registry names are only made canonical again, the others named again from their
affiliation (8 names ROR gave before ids were kept were named again by the rules so, on
2026-10-07). It took the affiliations without an institution from 2,785 to 122.

## Venues (`venue.py`)

The venue is detected once, when a paper is stored, from its comments and journal
reference; `make venues` applies a change to the stored papers, the archive's included.

- The venues of the table, `VENUES` (canonical name, kind, acronyms, full names), count
  unless the clause says the paper is not there (submitted, under review, prepared for,
  an extended version), or the venue's comma-separated part only mentions it (compared,
  ranked, rejected, an extension of, a benchmark): "CVPR 2018, Rank 1 in the ... Challenge"
  is a CVPR paper, "ranked 1st at the CVPR 2021 Challenge" is not.
- Requiring an acceptance cue instead, as the audit proposed, loses a venue in twenty:
  "40th Conference on Neural Information Processing Systems (NeurIPS 2026)", "Findings of
  EMNLP 2026".
- A full name is never the start of a longer one: VISAPP's "International Conference on
  Computer Vision Theory and Applications" and CVIP's "... and Image Processing" are not
  ICCV, IPTA and IPAS are not ICIP, and "Advances in Computer Vision and Pattern
  Recognition" (a book series) is not CVPR.
- Years of page ranges are not years ("TPAMI 2028" from pp. 2028-2040). Short years count
  ("CVPR16", "ECCV-18", "(MICCAI'22)"), and the major acronyms are read in any case once
  links are removed ("cvpr2019", "Neurips 2020"; never in "github.com/x/cvpr2018-code").
- Failing the table, an acronym followed by a year in a sentence of acceptance ("Presented
  at IEEE BIBM 2017").

### Published venues (Semantic Scholar)

`venue.published_venue` names the venue Semantic Scholar gives (`scholar.json`, see
[archive.md](archive.md)) as the table does: by one of its full names in the venue's name or venue
string, by its acronym in them ("ECCV Workshops"), or by an alternate name only for a venue
the table knows by acronym only, since another venue can share the acronym (the
International Conference on Information Photonics is "ICIP" too). Other venues keep
Semantic Scholar's name ("Information Fusion 2024"), never a bare venue string, which can
be an abbreviation ("Medical Image Anal."). Preprint servers are not venues.

The year comes from the proceedings' or journal's name ("2022 IEEE/CVF Conference on
..."), the venue string, the volume when it is a bare year, or an IEEE DOI
(10.1109/CVPR52688.2022.01234). Never from `publicationDate` or `year`, which are the arXiv
version's for a paper in four (66 of 235 in the spike), nor from a preprint's journal
("ArXiv", volume "abs/2006.05929"): a conference known only through its preprint has no
year ("NeurIPS").

On the site, the comments' venue wins where both exist: Semantic Scholar takes papers of
ICIP for the Information Photonics conference.

## Abstracts (`latex.py`)

arXiv abstracts are LaTeX, and every source gives them so (RSS, catchup pages, the API, the
HTML page's MathML as inline LaTeX, the catalog): `latex.plain_text` makes them plain text
where they are read, and `make venues` on the stored papers. Before it, 2,493 of 27,001
abstracts held a macro, and the search matched "textbf" for "text" (SRCH-19, decision 17).

- Text macros give their argument (`\textbf`, `\emph`, `{\em ...}`, `\underline`), `\url` its
  address, `\href` what it shows and, when that is not an address, where it leads; citations
  and labels go, with the space before them; a footnote goes in brackets.
- Math symbols give their character (`\times`, `\pm`, `\le`, Greek letters, `^\circ`), accents
  their letter (`B$\acute{\rm e}$zier`, `Schr\"odinger`), and `18--20` an en dash. A formula
  left with text only loses its dollars (`$\sim$18%` is "~18%"); one that still holds markup
  keeps them (`$S^2\times S^1$`). Math is not rendered.
- A paper's own macros (`\method`, `\ours`) stay as written: nothing says what they stand for.
  About 240 abstracts keep a backslash so, or in a formula.
