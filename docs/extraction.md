# Affiliations, venues and abstracts: how they are extracted

The rules behind `sources/arxiv_html.py` (affiliations and who is where), `venue.py`,
`latex.py` (abstracts as plain text) and their offline re-runs. Each came from a real page,
whose arXiv id is the evidence: never "simplify" one away without it.

## Ground rules

- Affiliations come from the API's submitter-declared ones, else from heuristics on
  LaTeXML's HTML front matter. Raw LaTeX is no option: `robots.txt` disallows `/e-print`
  and `/src` (export.arxiv.org disallows everything), and LaTeXML's HTML is parsed LaTeX.
- A fixture under `tests/fixtures/html/` for every new heuristic, its authors in
  `expected.json` first. After a deliberate change, `UPDATE_GOLDEN=1 uv run pytest
  tests/unit/test_golden_fixtures.py` rewrites `expected.json`: its diff is the review.
- Bump `EXTRACTOR_VERSION` with any change to what a page gives (affiliations, mapping):
  nothing else tells `reextract`, and only papers read again get it. A change to the
  cleaning alone (`clean_affiliation`) reaches stored strings through `make reclean`,
  then `make institutions`.
- Measure before and after with `make quality-affiliations` (`--page-cache-dir`: cached
  pages as stored and as extracted today) and `make stats`. Before a bump, read each paper
  `make extraction-diff` shows losing words: an author's name, noise, or a regression
  (2610.02974 lost "Alicante" to the "at" of an address).

## Sources, in order

- Contacts (`ltx_role_affiliation`, `ltx_role_address`) in `div.ltx_authors`, and beside
  them the numbered lines set as authors ("²Alibaba Group", 2610.12978). Anywhere, an
  affiliation glued to its author's name, a capital right after a listed name ("Xiaoya
  TangScientific Computing and Imaging InstituteUniversity of Utah", 2610.17412), the last
  of several names in one creator too ("Zheng Ge    Songtao Liu ... Jian SunMegvii
  Technology", ar5iv's 2107.08430), but never another author's name ("Huy V. VoMaximilian
  SeitzerFederico Baldassarre...", 2508.10104).
- `ltx_note`s of roles `address`, `institutetext` and `affiliation`, anywhere (Taylor &
  Francis' lettered list after the abstract, 2610.15403; BMVC's one institution, without
  saying whose, 2608.29904), and the article's own `footnotetext` notes led by a marker:
  those that name an institution in every piece, or whose pieces up to their
  correspondence sentence, those that clean to nothing aside, qualify as a thanks note's
  list (below): ICML's notice, "¹University of Tübingen. ²KAIST AI. Correspondence to: …",
  where "KAIST AI" names none and the correspondence ends the last piece (2610.35857,
  2610.35706, AFF-34). Its markers anchor the same pieces.
- Numbered lines after the names. A marker raised by a span's style is a superscript, and
  one set apart in spaces before a capital starts a line as one glued to the word does
  ("¹ NVIDIA ² MIT ³ UCB", one affiliation, its authors all at it, 2610.19495; AFF-37).
- Lines led by symbols ("*Oregon State University †The Ohio State University", 2610.17605)
  when at least half of those that are not noise name an institution and the others are no
  sentence nor role ("⋆Facebook AI †Sorbonne University", ar5iv's 2012.12877; symbols mark
  notes too: "†Now at Google", "‡Intern"); not when a line ends with one, the markers then
  trailing ("Independent§University of Waterloo¶", 2505.11293). One symbol's affiliation is
  never everyone's.
- "A is with B" sentences of thanks notes. What follows "is at" or "is with" is cut at its
  semicolons, a piece kept when it is a name: capitalized ("ETH Zurich"), naming an
  institution, ending with a country or holding a comma; not "the intersection of vision
  and language" of "This work is at the intersection of…" (AFF-9).
- In a block without contacts nor marked lines, the lines that name an institution or end
  with a country and hold no author's name (2610.18323: names in a table, then "Xi'an
  Jiaotong University"), the one affiliation everyone's only when nothing but names and
  noise was left out. Lines led by markers that hold only notes and names do not count
  as marked ("*corresponding authors: …" and names glued after a "*", 2508.10104). A row
  set apart in wide spaces is kept whole when one piece names an institution and none an
  author ("Meta AI Research    WRI    Inria", 2508.10104; "Southeast University    Tencent
  HY    UC Merced    Tsinghua University", 2610.14852, which gave two; AFF-37).
  "Foundation Model" is no institution (2609.21449). Where LaTeXML cut the author field at
  its commas and "and"s into creators ("University of Science", "Technology of China",
  2411.15633, 2510.11387), one naming no author with a piece of at most two words naming
  no institution nor country ("College Park", "Telecommunications"; not "(Guangzhou)")
  tells it: the block gives nothing rather than pieces. A piece is a creator's whole line,
  never part of a row set apart in wide spaces ("WRI", 2508.10104).
- Last, the affiliations a thanks note lists without a sentence (AFF-11), as IEEE
  conference classes (IROS) do: the whole note ("Department of Computer Science,
  University of Freiburg, Germany.", 2609.26325), a numbered note each ("¹FZI Research
  Center for Information Technology, …", 2609.03677), or numbered ones after other
  sentences, math markers printed as text with a modifier circumflex ("$ˆ1$University of
  Southern California, $ˆ2$Stanford University", 2609.16443). A note qualifies when no
  piece reads as a sentence ("is", "was", "work", "now", "funded"…) or is a web domain
  ("jzlab.org", 2610.00751), and at least half name an institution or end with a country
  ("UC San Diego" names none); never a funding or correspondence note ("German Research
  Foundation"). Last, so that it only fills a page that gave nothing.

A source that only names authors passes its turn: IEEE classes put the names in the
affiliation macro, the affiliations in thanks notes. The TeX source LaTeXML keeps beside
math (an `annotation`) is dropped first, else `$\dagger$` reads "†\dagger", which nothing
anchors (2610.12978, 2609.34299).

Thanks notes keep their source's line breaks ("are with the School of" / "Intelligent
Engineering and Automation", 2609.33097; 2608.30657 gave "School of Mechanical and"): a
line continues the previous one unless that one ends with `.;:!?` or it starts a usual
note ("Manuscript", "Corresponding"…), a marker ("* Equal Contribution") or a new "B is
with", though a wrapped list of people joins ("Bo Zheng, …, Weinan Guan," / "Zhiheng Li,
… are with", 2609.15562).

## Cleaning

- Several "is with" sentences on a line: each affiliation ends at the last full stop before
  the next sentence, initials skipped ("..., Spain. L. Zhinin is with"), so that its
  abbreviations survive ("Dept. of CS, MIT, USA"). "A and B are with X" gives X anywhere,
  affiliation macros included, unless what precedes the verb names an institution; so does
  a role in an affiliation macro ("Manoj Karnekar is Robotics Lead at FloMobility Pvt.
  Ltd.", 2610.05505), not in thanks notes ("is available at"). IEEE's "X, China, and also
  with Y" gives the author both (`clean_affiliations` returns every affiliation of a
  string, 2609.00814).
- Author names printed as affiliations ("Benoît Macq Fellow, IEEE") are dropped
  (`names_only_authors`, by `name_key`), not strings with an institution word nor
  collectives ("Alzheimer's Disease Neuroimaging Initiative"); the one affiliation left
  then is not everyone's (2609.38180).
- Contact details go, the affiliation before them stays: an "Email:" label glued to the
  country ("..., MI, USAEmail: {...}@wayne.edu", 2608.29996); obfuscated addresses ("jane
  (at) example.org", "lab [at] example.org"); mailbox lists ("{jane.doe, john.roe}"), also
  before their domain ("..., Germany. {jane.doe, jroe}@tum.de", 2610.03283) or a full
  stop ("..., Italy. {name.surname}@unitn.it.", 2609.28184), or glued to the country
  ("..., Singapore{jane,john}@nus.edu.sg", 1312.4400); an address in brackets and
  what follows, ending an unwrapped thanks note's sentence ("..., Hong Kong SAR, China
  (author@...)", 2609.10082), or ending a line ("..., Vienna, Austria author@...",
  2610.02974). A list cut across two contact nodes, glued to the next affiliation
  ("{jane.doe,...,jdoe," then "Apple", 2410.23054), ends before a capital;
  mailboxes may hold underscores ("john_roe"), and capitals when dots or underscores
  join their parts ("{Jane.Doe, A.Roe,", 2610.25235), never an affiliation's words. A
  string still holding a contact detail is dropped whole (`has_contact`, as in
  `validate`): a page the rules miss loses one string, not a day of papers.
- `_JUNK_RE` rejects the rest: lone words ("the", "dot"), link and contribution leftovers
  ("Code", "Core Contributors"), cut-off units ("School of"), lone countries, and IEEE's
  template author, "IEEE Publication Technology Department" (2312.17663).
- Superscript markers split affiliations, but not between two lowercase letters
  ("Hyper<sup>2</sup>labs"). Every `<br>` is a line break, newline or not, and so is the
  spacing of one printed as text (`[5pt]`, `[0.2em]`, from `\\[5pt]`).
- IEEE classes lose some line breaks ("Dept. of Computer ScienceUniversity of Alabama",
  2609.00446): `clean_affiliation` puts a comma where a lowercase letter meets a
  capitalized word, or a closing bracket a word, after a unit word of the same part; never
  inside brackets ("(ShenZhen)") nor after a hyphenated word ("AnimSchool", "ByteDance",
  "McGill" stay). It would split "AI Lab of ByteDance", which no stored string holds.
- A line ending with "," or "and" continues on the next; one naming only a place joins a
  previous one without a country, and so does an address without its country, a number of
  its own on it ("Zalando Research" / "Mühlenstraße 25, 10243 Berlin", 1708.07747, as
  older pages lay contacts out; not "42dot by Hyundai", 2610.11060; AFF-37); one starting with "and" continues the unit ending the
  previous one ("Faculty of Medicine" / "and Health Sciences", 2610.03290), not an
  institution ("Stanford University" / "and Mila"), nor when "&" starts it ("&
  Canada-CIFAR AI Chair"). A line naming only authors never joins the next ("Terrence
  Chen, Ziyan Wu" / "United Imaging Intelligence, Boston MA, USA", 2610.02382).
- A line ending with a lowercase preposition after a space continues on the next, unless a
  marker starts it ("Key Laboratory ... of Ministry of" / "Education, Jilin University",
  2609.11477); not "TU Wien, AT" (a country code) nor the domain of
  "author@technikum-wien.at" (2610.02974).
- A unit without its institution (a unit word, in French too, "Département d'…", 1411.1784;
  no institution word, no comma: `is_bare_unit`, also a quality sign) takes the next line ("Department of Computer
  Science, Dartmouth College, Hanover, NH, USA", 2609.38705, AFF-10), unless that line
  starts with a marker, is another unit ("Department of ECE" / "Department of CS" /
  "University of Central Florida": the second gets it, 2610.02000) or a note
  ("Corresponding author", which would make the whole string noise).
- An author's contact nodes are read as one text's lines, by the extraction and the
  per-creator tier alike (IEEE conference classes make each address line a node); those of
  different authors never join ("Department of Computer Science, University of Alabama at
  Birmingham" / "Birmingham, AL, USA", spread over a table, 2609.13271).
- Numbered markers written as text split a string ("Cornell University 2University of
  California, Berkeley", AFF-23; after wide spaces, "1Roblox  2Carnegie Mellon
  University", 2402.13251): one or two digits glued to a capitalized word ("3HKUST",
  "4eBay") after a space, the word before holding no digit or itself marked ("2CASIA
  3HKUST"), so that postcodes ("London WC1E 6AE", "QC H2S 3H1"), "3D" and "4K" stay
  whole. `reclean` splits stored strings too.
- Leading digits are markers unless they start a name ("54th Research Institute", "3M
  Company", "3D Vision Lab", "4K"), in strings and numbered lines ("2 3D Vision Lab").
- Link labels ("Project page", "Project Website") are stripped, not dropped: once the URL
  goes, the label is often glued to the affiliation ("MITProject page"). Correspondence,
  phone numbers ("Tel.: +49 ...") and placeholders ("TODO: ...") are noise; a LaTeX
  command printed as text goes ("\\addrDepartment of ...", 2610.04051), glued to the number
  of its marker too ("\\affilnum1Department of ...", SAGE's template, 2610.18363;
  "\\authormark2…", 2505.14715), as does the TeX source a string read before
  `_ANNOTATION_RE` holds after its symbol ("Φ\\Phi-lab", 2609.06187), not a name's own
  backslash ("Institute of Creative\\Media/Technologies", 2608.29287). Templates'
  placeholders are junk ("Author Affiliation(s)", 2610.01890; "Affiliation", "Address",
  2610.27759), their example authors noise ("Cranberry-Lemon University", "University of
  the Witwatersrand, Joburg"; not the real one's "Johannesburg", 2405.01828), and a note on
  the affiliations glued to the last one goes ("…(DKFZ), Full affiliations are given in
  Appendix", 2411.03670) (AFF-35). A contribution note glued to the affiliation after it
  goes, the affiliation stays ("Equal senior contributionsDeepMind", ar5iv's 2204.14198).
- elsarticle's `organization=…, city=…, country=…`, printed verbatim, ignores line breaks:
  a repeated key starts the next affiliation, and `clean_affiliation`, only (the mapping
  looks affiliations up through it), makes the rest plain values, organization first.
- The countries are those affiliations write (AFF-18) but people's names (Jordan, Chad,
  Georgia), which end lines of names, and Wales ("New South Wales"); US states are none,
  their codes being words ("IN", "OR", "ME"), so "Pittsburgh, PA 15213" is no place. A
  name ending with a country without a comma ("National Research Council Canada") takes a
  place in that country ("London, ON, Canada", 2609.12374), not another ("University of
  Luxembourg" / "Trier, Germany", 2609.06629). The institution rules' `_COUNTRY_RE` is
  built from the same `COUNTRIES`.
- A list cut after its connector loses it ("The University of Hong Kong, and"), as does a
  trailing dash; a name cut short keeps its "and" ("Nanjing University of Posts and").

## Who is where: the author mapping

The mapping reuses the same nodes, in tiers: per-creator contacts, superscript markers
matched with the lines they lead (or trail), "A is with B" sentences (thanks notes and
affiliation contacts: 2609.06721 writes them in the last author's block), and the single
affiliation or author. A wrong pair is worse than none: an ambiguous name alignment drops
the whole tier, and unresolved authors stay `null`.

- One affiliation is everyone's unless its source left lines out or it came from "A is
  with B" sentences, which place whom they name ("A. Doe is with MIT"), "The authors"
  everyone (AFF-9).
- Thanks notes' numbered markers anchor the authors' ("¹FZI Research Center…",
  2609.03677); their own mark, the same "†" for every note, anchors nothing, nor do
  funding and correspondence notes.
- Not creators: links set as authors ("Project Page", a repository, 2609.37107),
  addresses, and lines led by a marker naming no author ("²Alibaba Group", "✉Corresponding
  author", 2610.12978, whose last person alone holds "¹Sun Yat-sen University": the
  markers place everyone). A creator an affiliation is glued to is that author, the
  affiliation its contact (2610.17412).
- A marker glued to the word after a name introduces an affiliation line: "Bob Smith⟨2⟩
  ⟨1⟩Stanford University" places Bob at 2 only. In free-form blocks it also starts a
  numbered line, for affiliations and anchors ("University of California, Berkeley
  ⟨2⟩Duke University ⟨3⟩Carnegie Mellon University", 2609.38079).
- Symbols come off a marker's number ("⟨2,6*‡⟩" is 2 and 6), "∗" (`\ast`) is a note like
  "*" (2609.35052), and known markers without separators ("12", "⋆†") are read one by one;
  in an anchor, all mark the text after them ("⟨*⟩⟨†⟩⟨‡⟩ Y. Yang and J. Bos are with the
  Department of ..." anchors * and ‡, 2610.13891, 2610.13872, AFF-33).
- Anchors match affiliations regardless of commas ("Department of Computer Science
  University of Central Florida", 2610.02000). A marker's text runs to the next marker:
  an affiliation's joined lines, then another of the same marker ("⟨2⟩Laboratory … Response
  / Technologies (LiGHT) / Swiss Federal Institute of Technology (EPFL), …", 2610.03290).
  Cleaning to no affiliation, it is cut into the paper's affiliations, one after another;
  a text not wholly made of them anchors nothing.
- Per-creator contacts place nobody when only the last creator has any: LaTeXML gives it a
  block shared by all (2609.37098, 2609.00866: its 25 affiliations to its 55th author).
- Out of the per-creator tier: a creator naming several people ("A, B and C", "A & B";
  2609.05583, then placed by its markers) or holding several authors' names without
  separator (2610.01434, apart by wide spaces). But a pair without comma nor markers
  ("Zhiyuan Yang & Jiahao Cheng") beside other creators shares its block (2609.36407),
  unless that block only names a place, the end of an address the creators before began
  ("Orlando, FL 32816, USA", 2609.34021).

## Institutions (ROR, then `institutions.py`)

`api.ror.org/v2/organizations?affiliation=` marks one match `chosen`, kept only when one of
its names (not an acronym) of at least two words appears word for word in the affiliation:
`chosen` alone matched "ARC Lab, Tencent" to an association called ARC and "180 Queen's
Gate" to "The Gate". A candidate with a name holding the chosen one's, written whole in the
affiliation (hyphens and dashes splitting words), wins (`_longer_match`, AFF-30): "Texas A&M
University-Kingsville" chose Texas A&M University (score 1.0) over Texas A&M University –
Kingsville (0.95). ROR names about 70% of the strings, with their ids (`institution_ids`).
A failing ROR never fails a run: lookups stop and resume next run. A string ROR answered
before is not asked again (`collect.ror_answers`, AFF-17), its latest answer read from the
day files: an institution with an id is ROR's match, one without the rules'.

`institutions.name_institutions` names the rest (AFF-13, decision 12; the site names none),
keeping the most institution-like part between commas, a university over an organization
over anything else, a unit or an address alone naming nothing ("School of Computer
Science, Peking University" is Peking University). A known acronym alone is its
institution as ROR names it ("CMU", `ACRONYMS`, the same in the site's search by
`test_the_site_knows_the_same_acronyms`), and so is one before one of its units ("KAIST
AI", "KAIST College of AI", "CUHK MMLab", "ETH AI Center", 92 institutions named apart
until AFF-36), written with two capitals at least ("Hit Robot Group" is none); not before a joint entity ("MIT-IBM Watson AI Lab", "KAIST & AITRICS"), another
campus ("HKUST (GZ)", an acronym of its own), a hospital ("TUM Klinikum") nor another
university ("CUHK The University of Adelaide HKUST"). Some names are written alone as
acronyms are ("UCB", "Oxford", "Harvard", 2610.19495); those of places too (Oxford,
Stanford, Princeton) name their university only as the best part, not in "Ultromics Ltd,
Oxford, UK"; `validate` warns of one whose name no
institution with an id has ("University of California, San Diego": ROR has no comma). A
company mentioned anywhere is the company ("ARC Lab, Tencent IEG" is Tencent), not a
hospital named after it; a University of California campus keeps its city. ROR's and
OpenAlex's names go through `canonical` too, a company's subsidiaries ("Google
(Switzerland)") being the company. One of the paper's own authors is never an
institution. What `_JUNK_RE` now rejects, in records extracted before it, mostly names
none: `institution_name` has its own narrower `_JUNK_RE` and `_COUNTRY_RE`, and a
department, school or faculty is no institution; a cut-off "Institute of" would name
itself, but none is stored (`make reclean` drops them from day files).

An institution with a ROR id came from ROR (or OpenAlex, in the archive, whose registry
names may have none); one without, from the rules. `make institutions-again` names stored
institutions again after a change to the rules: registry names are only made canonical
again, the others named again from their affiliation.

## Venues (`venue.py`)

Detected once, when a paper is stored, from its comments and journal reference; `make
venues` applies a change to stored papers, the archive's included.

- The venues of `VENUES` (canonical name, kind, acronyms, full names) count unless the
  clause says the paper is not there (submitted, under review, prepared for, an extended
  version) or the venue's comma-separated part only mentions it (compared, ranked,
  rejected, an extension of, a benchmark): "CVPR 2018, Rank 1 in the ... Challenge" is a
  CVPR paper, "ranked 1st at the CVPR 2021 Challenge" is not. Requiring an acceptance cue
  instead loses a venue in twenty ("Findings of EMNLP 2026").
- A full name is never the start of a longer one: VISAPP's "International Conference on
  Computer Vision Theory and Applications" and CVIP's "... and Image Processing" are not
  ICCV, IPTA and IPAS are not ICIP, "Advances in Computer Vision and Pattern Recognition"
  (a book series) is not CVPR.
- Page ranges are not years ("TPAMI 2028" from pp. 2028-2040). Short years count
  ("CVPR16", "ECCV-18", "(MICCAI'22)"), and major acronyms are read in any case once links
  are removed ("cvpr2019", "Neurips 2020"; never "github.com/x/cvpr2018-code").
- Failing the table, an acronym and a year in a sentence of acceptance ("Presented at IEEE
  BIBM 2017").

### Published venues (Semantic Scholar)

`venue.published_venue` names Semantic Scholar's venue (`scholar.json`,
[archive.md](archive.md)) as the table does: by a full name in the venue's name or string,
by its acronym there ("ECCV Workshops"), or by an alternate name only for a venue known by
acronym only, since venues share acronyms (Information Photonics' conference is "ICIP"
too). Others keep Semantic Scholar's name ("Information Fusion 2024"), never a bare venue
string, which can be an abbreviation ("Medical Image Anal."). Preprint servers are not
venues. The year comes from the proceedings' or journal's name ("2022 IEEE/CVF Conference on
..."), the venue string, a volume that is a bare year, or an IEEE DOI
(10.1109/CVPR52688.2022.01234); never from `publicationDate` or `year`, the arXiv
version's for a paper in four, nor a preprint's journal ("ArXiv", volume
"abs/2006.05929"): a conference known only through its preprint has no year ("NeurIPS").
On the site, the comments' venue wins: Semantic Scholar takes ICIP papers for Information
Photonics.

## Abstracts (`latex.py`)

Every source gives abstracts as LaTeX (RSS, catchup pages, the API, the HTML page's MathML
as inline LaTeX, the catalog): `latex.plain_text` makes them plain text where they are
read, and `make venues` on stored papers. Before it, 2,493 of 27,001 held a macro, and the
search matched "textbf" for "text" (SRCH-19, decision 17).

- Text macros give their argument (`\textbf`, `\emph`, `{\em ...}`, `\underline`), `\url`
  its address, `\href` what it shows and, when that is not an address, where it leads;
  citations and labels go, with the space before them; a footnote goes in brackets.
- Math symbols give their character (`\times`, `\pm`, `\le`, Greek letters, `^\circ`),
  accents their letter (`B$\acute{\rm e}$zier`, `Schr\"odinger`), `18--20` an en dash;
  math is not rendered. A formula left with text only loses its dollars (`$\sim$18%` is
  "~18%"), before the groups go, else a group around it keeps its braces (`{8$\times$}`
  gave "{8×}", 2609.23733); one still holding markup keeps them (`$S^2\times S^1$`).
- Reading plain text again changes nothing (`make venues` reads stored abstracts again;
  `test_latex.py` checks every case). An escaped dollar is a price, kept bare, so two
  dollars are no formula when what lies between holds a space and a digit follows the
  second (`$300,000 ($26,000 vs. $320,000)`, 2310.00426); a symbol still is one
  (`$\sim$18`).
- A paper's own macros (`\method`, `\ours`) stay as written: nothing says what they mean.
