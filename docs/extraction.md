# Affiliations, venues and abstracts: how they are extracted

The rules behind `sources/arxiv_html.py` and the `affiliations/` package (affiliations and
who is where), `venue.py`,
`latex.py` (abstracts as plain text) and their offline re-runs. Each came from a real page,
whose arXiv id is the evidence: never "simplify" one away without it.

## Ground rules

- Affiliations come from the API's submitter-declared ones, else from heuristics on
  LaTeXML's HTML front matter. Raw LaTeX is no option: `robots.txt` disallows `/e-print`
  and `/src` (export.arxiv.org disallows everything), and LaTeXML's HTML is parsed LaTeX.
- A fixture under `tests/fixtures/html/` for every new heuristic, its authors in
  `expected.json` first. After a deliberate change, `UPDATE_GOLDEN=1 uv run pytest
  tests/unit/test_golden_fixtures.py` rewrites `expected.json`: its diff is the review.
  `versions.json` beside it keeps the version under which each fixture's output last
  changed, and the rewrite refuses an output that changed under that same version (EXT-8):
  bump `EXTRACTOR_VERSION` first. `UPDATE_GOLDEN=unreleased` writes them again under a
  version that has not reached `main` yet.
- Bump `EXTRACTOR_VERSION` with any change to what a page gives (affiliations, mapping):
  nothing else tells `reextract`, and only papers read again get it. A change to the
  cleaning alone (`clean_affiliation`) reaches stored strings through `make reclean`,
  then `make institutions`.
- Measure before and after with `make quality-affiliations` (`--page-cache-dir`: cached
  pages as stored and as extracted today), `make gold-affiliations` (60 papers read by
  hand, exact match per layer: what the extraction should give, where the golden fixtures
  pin what it gives) and `make stats`. Before a bump, read each paper
  `make extraction-diff` shows losing words: an author's name, noise, or a regression
  (2610.02974 lost "Alicante" to the "at" of an address).
- Coverage cannot see a rule written as one alternative of a regular expression. `make
  knockout` (`tests/knockout.py`, about 7 minutes on 10 cores) makes each expression of
  the extraction, then each of its top-level alternatives, never match, and runs the
  extraction's tests: those it leaves green no test asserts on; replayed on the cached
  pages and the stored strings, a `LIVE` one changes what they give, a rule the next bump
  could lose unseen. Run it before a bump, and give each live one a fixture or a named
  test (EXT-2). An `untested` one that changes nothing guards pages the cache does not
  hold.

## Sources, in order

- Contacts (`ltx_role_affiliation`, `ltx_role_address`) in `div.ltx_authors`, and beside
  them the numbered lines set as authors ("²Alibaba Group", 2610.12978). Anywhere, an
  affiliation glued to its author's name, a capital right after a listed name ("Xiaoya
  TangScientific Computing and Imaging InstituteUniversity of Utah", 2610.17412), the last
  of several names in one creator too, spaced or glued to each other ("Zheng Ge    Songtao
  Liu ... Jian SunMegvii Technology", ar5iv's 2107.08430; "...Ismail Ben AyedJose DolzÉTS
  Montreal", 2312.12730), but never another author's name ("Huy V. VoMaximilian
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
  ("¹ NVIDIA ² MIT ³ UCB", one affiliation, its authors all at it, 2610.19495; AFF-37), and
  so does one ending a span of text, before the text after the span ("ZJU<span>
  ²</span>Video Rebirth", 2605.09681, which placed nobody), not one ending a name's span
  (AFF-40).
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
  set apart in wide spaces is kept whole when one piece names an institution or a
  collective and none an author ("Meta AI Research    WRI    Inria", 2508.10104;
  "Southeast University    Tencent HY    UC Merced    Tsinghua University", 2610.14852,
  which gave two; AFF-37; "Qwen Team  Alibaba Group", 2409.12191, AFF-38).
  "Foundation Model" is no institution (2609.21449); a company named after its AI is one
  ("Stability AI" under a table of names, 2311.15127; capitals required, "Ai" being a given
  name; AFF-40). Where LaTeXML cut the author field at
  its commas and "and"s into creators ("University of Science", "Technology of China",
  2411.15633, 2510.11387), one naming no author with a piece of at most two words naming
  no institution nor country ("College Park", "Telecommunications"; not "(Guangzhou)")
  tells it: the block gives nothing rather than pieces. A piece is a creator's whole line,
  never part of a row set apart in wide spaces ("WRI", 2508.10104).
- A page signed by organizations rather than its authors: when no creator names a listed
  author and each names an institution or a collective, they are the paper's affiliations,
  nobody placed ("Qwen Team", "Alibaba Group", 2502.13923; "BeingBeyond Team",
  2610.11283; AFF-38). Not when one may be a person the page spells otherwise ("A.
  Lovelace") or a place.
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
  affiliation macros included, unless what precedes the verb names an institution (a word
  starting as one does, not "Ahmad El-Sallab", 1808.02350); so does
  a role in an affiliation macro ("Manoj Karnekar is Robotics Lead at FloMobility Pvt.
  Ltd.", 2610.05505), not in thanks notes ("is available at"). IEEE's "X, China, and also
  with Y" gives the author both (`clean_affiliations` returns every affiliation of a
  string, 2609.00814).
- Author names printed as affiliations ("Benoît Macq Fellow, IEEE") are dropped
  (`names_only_authors`, by `name_key`), their markers read as text left out ("Saining Xie
  1", 2406.18533; "Kai Wang2", 2610.17877), not strings with an institution word nor
  collectives ("Alzheimer's Disease Neuroimaging Initiative"); the one affiliation left
  then is not everyone's (2609.38180). A dotless "ı", which the listing writes for LaTeX's
  `\'{\i}`, folds as "i": the listing's "Alvaro Garcıa" is the page's "Álvaro García"
  (2505.12089).
- Where an author went since or interned is a note ("now at Microsoft Research",
  2202.07643; "Interns at Shanghai AI Laboratory", 2505.23656; "Done as intern at Zhipu
  AI", 2311.03079): the cleaning drops it, and the tiers still read such a line as a
  sentence ("†Now at Google" tells that symbols mark notes).
- A mailbox or a mail domain printed without its "@" is a contact detail too ("gmail.com",
  "mails.tsinghua.edu.cn", a lone "wangbohua.wbh"; not "valeo.ai", a lab, EXT-3), for the
  cleaning and `validate` alike (`has_contact`).
- Contact details go, the affiliation before them stays: an "Email:" label glued to the
  country ("..., MI, USAEmail: {...}@wayne.edu", 2608.29996); obfuscated addresses ("jane
  (at) example.org", "lab [at] example.org"); mailbox lists ("{jane.doe, john.roe}", each
  name matched whole and once, so that a long list ending on nothing the rule takes is
  read in linear time, EXT-1), also
  before their domain ("..., Germany. {jane.doe, jroe}@tum.de", 2610.03283) or a full
  stop ("..., Italy. {name.surname}@unitn.it.", 2609.28184), or glued to the country
  ("..., Singapore{jane,john}@nus.edu.sg", 1312.4400); an address in brackets and
  what follows, ending an unwrapped thanks note's sentence ("..., Hong Kong SAR, China
  (author@...)", 2609.10082), or ending a line ("..., Vienna, Austria author@...",
  2610.02974), or in a span of text glued to the word before it, set apart first
  (`University of Oxford<tt>author@...</tt>` lost "Oxford", ar5iv's 2006.13662; in italics,
  "University of Washington", 2412.06141; an "@" in a span of its own stays glued,
  2609.13233), or glued to it in the LaTeX source, after the last word of a name or a
  country, which a space sets apart ("Technion - Israel Institute of
  Technologyauthor@…" gave "… Institute of", 2006.14610; "Zhejiang Universityauthor@…"
  gave "Zhejiang", 2011.00147; AFF-41). Several addresses at the end go together, which
  a comma after the first joined across lines: "University of California Santa
  Cruz{…}@…," then "a@…, b@…" gave nothing (2406.18522), nor did DreamFusion's "Google
  Research, UC Berkeley" (2209.14988). ORCID identifiers go with their label ("(ORCID:
  0000-…)", 2305.17033; "ORCID codes: FT 0009-…; …", 2610.13604; "ORCID" alone,
  2610.26079). A list cut across two contact nodes, glued to
  the next affiliation ("{jane.doe,...,jdoe," then "Apple", 2410.23054), ends before a
  capital; mailboxes may hold underscores ("john_roe"), and capitals when dots or
  underscores join their parts ("{Jane.Doe, A.Roe,", 2610.25235), never an affiliation's
  words. A string still holding a contact detail is dropped whole (`has_contact`, as in
  `validate`): a page the rules miss loses one string, not a day of papers.
- `_JUNK_RE` rejects the rest: lone words ("dot"), link and contribution leftovers
  ("Code", "Core Contributors"), a unit's word alone ("School", "Department"), lone
  countries, and IEEE's template author, "IEEE Publication Technology Department"
  (2312.17663). A unit cut after its preposition ("School of", "Center for"), and "the",
  "an" or "of" alone, are rejected before it, as dangling (`_DANGLING_RE`), a connector
  or too short: those words of `_JUNK_RE` only back them up.
- The cleaning reads every source's residues, not only the one where they were first met
  (EXT-4, version 23): a marker LaTeXML printed as text, its math unparsed, starts an
  affiliation wherever it is ("$1$ University of Technology Nuremberg", "$^a$ X; $^b$ Y"
  is two); format characters (Unicode's Cf, zero-width spaces before "Tsinghua
  University", 2303.10137) go, and LaTeX's tilde printed as U+02DC is a space; a note's
  sentence on its own is none ("This work was done when the author was at Adobe
  Research"): it starts as notes do, its second word lowercase, and says what notes say.
- One vocabulary each (EXT-7): the marker symbols are `_NOTE_SYMBOLS` (notes: `*`, `†`,
  `#`…) and those classes mark affiliations with (`♠`, `★`), from which every marker
  pattern is built, so that none leads an affiliation; a line of names is one even when a
  name holds an institution's word ("Slabaugh"), since only words that start like one
  count there; and names fold as everywhere else (`letters.PLAIN_LETTERS`: "Bartłomiej"
  is "Bartlomiej"). "Babeș-Bolyai University" stored as "Babe" and "-Bolyai University"
  (2610.19993) is split in the page itself: its page is not in the local cache.
- Superscript markers split affiliations, but not between two lowercase letters
  ("Hyper<sup>2</sup>labs"). Every `<br>` is a line break, newline or not, and so is the
  spacing of one printed as text (`[5pt]`, `[0.2em]`, from `\\[5pt]`).
- IEEE classes lose some line breaks ("Dept. of Computer ScienceUniversity of Alabama",
  2609.00446): `clean_affiliation` puts a comma where a lowercase letter meets a
  capitalized word, or a closing bracket a word, after a unit word of the same part, the
  part counted from the last cut ("Research LabDepartment of … ScienceTexas A&M" is cut
  twice, 2609.22631); never inside brackets ("(ShenZhen)") nor after a hyphenated word
  ("AnimSchool", "ByteDance", "McGill" stay). It would split "AI Lab of ByteDance", which no
  stored string holds. Older LaTeXML, as ar5iv's, loses an affiliation's line breaks too
  (AFF-40): a cut also follows a company's suffix ("ByteDance IncShanghai", 2309.02301) and,
  after a name of several words, comes before an institution's first word or a country
  ending its part ("Visual Geometry GroupUniversity of OxfordUK", 2206.07045; "Google
  DeepMindUniversity College London", 2512.08924), not after a word starting such names, a
  space lost after it ("Shenzhen KeyLaboratory of Media Security", 2509.25502;
  "NationalUniversity"). Two capitals only start a country: "Department of CSRPI" stays.
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
  ("Corresponding author", which would make the whole string noise); a line the next one
  goes on still counts ("School of SE" / "Huazhong University of Science and" /
  "Technology", 2610.23250). A numbered line takes the lines after it that go on with it,
  up to the next marker, for affiliations and anchors alike: a block setting each one as
  table rows ("¹ Department of Computer Science" / "Stony Brook University") kept the unit
  alone (2609.38607, 2609.33449, AQ-3).
- An author's contact nodes are read as one text's lines, by the extraction and the
  per-creator tier alike (IEEE conference classes make each address line a node); those of
  different authors join only as one block LaTeXML spread over them, its end a creator
  naming a place and nothing else but e-mails, none before ending with its country
  ("Department of Computer Science, University of Alabama at Birmingham" / "Birmingham,
  AL, USA" / the e-mails, 2609.13271; 2609.06726, 2609.34021, AQ-5): read as one,
  everyone at it. Whole addresses each ending with its country are each author's own
  ("HeartFlow, California, USA", 1804.03999).
- Numbered markers written as text split a string ("Cornell University 2University of
  California, Berkeley", AFF-23; after wide spaces, "1Roblox  2Carnegie Mellon
  University", 2402.13251): one or two digits glued to a capitalized word ("3HKUST",
  "4eBay") after a space, the word before holding no digit or itself marked ("2CASIA
  3HKUST"), so that postcodes ("London WC1E 6AE", "QC H2S 3H1"), "3D" and "4K" stay
  whole, nor after a preposition ("Faculty of 3mE", TU Delft, 2203.10157). `reclean` splits
  stored strings too.
- Universities run together, their line breaks lost (ar5iv's pages, several authors in
  one creator), are set apart (AFF-41): after a name ending in "University", one of a word
  and "University" ("Tianjin University Wuhan University", 1902.10859); after "University
  of" and a word, one of a word and "University" not followed by "of" ("The University of
  Adelaide Peking University Huazhong University of …", 1904.04514), as "University of
  Southern California University of Washington" cuts elsewhere (2311.17946, left whole);
  after a university's country, a university, institute or college ("Linköping University,
  Sweden University of Central Florida", 2006.09785), unless that country starts names of
  its own ("…, China University of Mining and Technology").
- Leading digits are markers unless they start a name ("54th Research Institute", "3M
  Company", "3D Vision Lab", "4K"), in strings and numbered lines ("2 3D Vision Lab").
- Link labels ("Project page", "Project Website") are stripped, not dropped: once the URL
  goes, the label is often glued to the affiliation ("MITProject page"); "Project:" with its
  colon too ("Li YuanProject: <url>" gave "Project", 2406.18522). Correspondence,
  phone numbers ("Tel.: +49 ...") and placeholders ("TODO: ...") are noise; a LaTeX
  command printed as text goes ("\\addrDepartment of ...", 2610.04051), glued to the number
  of its marker too ("\\affilnum1Department of ...", SAGE's template, 2610.18363;
  "\\authormark2…", 2505.14715), as does the TeX source a string read before
  `_ANNOTATION_RE` holds after its symbol ("Φ\\Phi-lab", 2609.06187), not a name's own
  backslash ("Institute of Creative\\Media/Technologies", 2608.29287). Templates'
  placeholders are junk ("Author Affiliation(s)", 2610.01890; "Affiliation", "Address",
  2610.27759; CVPR's "Institution2", 2309.04907), their example authors noise
  ("Cranberry-Lemon University", "University of the Witwatersrand, Joburg"; not the real
  one's "Johannesburg", 2405.01828), and their creators go whole, with "Department of
  Computer Science" and "Pittsburgh, PA 15213" beside the university, which every author
  of 2502.10841 and 2610.27759 was placed at (AFF-40), and a note on
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
  trailing dash. A string ending in "and" or "&" without a comma lost what LaTeX's `\and`
  ended it with (AFF-41): what precedes stands alone ("The University of Texas at Austin
  and", 2410.14919; "Faculty of Mathematics and Computer Science and", 2503.08373; "ECE &",
  2610.16337), unless it is a name cut short, which a word like "Science", "Technology" or
  "Posts" ends outside a unit ("Hong Kong University of Science and", "Nanjing University
  of Posts and"): such a string goes, and so does one ending in a preposition ("Technion -
  Israel Institute of", "Deutsches Forschungszentrum für", 2609.35150), whose name no rule
  can guess; the institution rules named "Hong Kong University of Science and" the
  University of Hong Kong (2306.04344).

## Who is where: the author mapping

The mapping reuses the same nodes, in tiers: per-creator contacts, superscript markers
matched with the lines they lead (or trail), "A is with B" sentences (thanks notes and
affiliation contacts: 2609.06721 writes them in the last author's block), and the single
affiliation or author. A wrong pair is worse than none: an ambiguous name alignment drops
the whole tier, and unresolved authors stay `null`.

- One affiliation is everyone's unless its source left lines out or it came from "A is
  with B" sentences, which place whom they name ("A. Doe is with MIT"), "The authors"
  everyone (AFF-9). Initials name the one author they fit, the surname glued to the
  initial's full stop too ("Z.Dong, Y.Sun, T.Liu, and Y.Gu are with …", 2410.08613).
- Thanks notes' numbered markers anchor the authors' ("¹FZI Research Center…",
  2609.03677); their own mark, the same "†" for every note, anchors nothing, nor do
  funding and correspondence notes.
- Not creators: links set as authors ("Project Page", a repository, 2609.37107),
  addresses, and lines led by a marker naming no author ("²Alibaba Group", "✉Corresponding
  author", 2610.12978, whose last person alone holds "¹Sun Yat-sen University": the
  markers place everyone). A creator an affiliation is glued to is that author, the
  affiliation its contact (2610.17412).
- A marker glued to the word after a name introduces an affiliation line: "Bob Smith⟨2⟩
  ⟨1⟩Stanford University" places Bob at 2 only; so does the last of a run followed by a
  known affiliation, after a line break ("Hieu Le⟨2⟩ ⟨1⟩ Department of Computer Science,
  Stony Brook University", 2609.38607). A footnote mark beside markers written by hand
  points to a note ("Equal contribution"), not an affiliation of its number (2609.39548,
  2609.24787, AQ-2); alone, it may point to an affiliation's footnote. In free-form blocks it also starts a
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

## Extraction versions

`EXTRACTOR_VERSION` (`sources/arxiv_html.py`), stored with the affiliations a page gave;
what each version changed:

- 1: the first version kept (October 2026).
- 2: leading numbers of names kept ("54th", "3M"), superscripts inside a word and line
  breaks without a newline read as written, links in the author list are not authors, and
  a marker that starts an affiliation line is not the previous name's.
- 3: thanks notes read across the line wraps of their source, numbered markers glued to
  the next affiliation start one ("Cornell University ²Duke University"), a unit without
  its institution joined to the next line, an author's contact nodes read as one text,
  and markers mixing a number and symbols ("2,6*‡") read as the number.
- 4: a line that only names authors is never joined to the next, anchors match the lines
  their affiliation was joined from, a line starting with "and" continues the previous
  one, a creator holding several authors' names is never one person, and the people of
  an "A & B" creator share its block, and an address in brackets ends an affiliation
  rather than dropping it.
- 5: a line ending with a preposition ("Ministry of") continues on the next one, a place
  completes a name that ends with a country ("National Research Council Canada"), and
  places end with many more countries (AFF-18).
- 6: a preposition ends a line only after a space, not the domain of an address
  ("technikum-wien.at"), and an address at the end of a line ends its affiliation.
- 7: so does a list of mailboxes before its domain ("{a, b}@tum.de"), and "X is Robotics
  Lead at Y" gives Y, as "X is with Y" does.
- 8: affiliation notes are read (2610.15403), and so are numbered lines set as authors
  (2610.12978), an affiliation glued to its author's name (2610.17412), lines led by
  symbols that each name an institution (2610.17605) and, last, the lines of a block
  without markers that name one (2610.18323); addresses and marker lines set as authors
  are nobody, markers written in math are read without their TeX source, and an address
  before a full stop (2609.28184) or after a glued "Email:" label (2608.29996) ends its
  affiliation.
- 9: what version 8 got wrong on the archive's pages (2026-10-15): names glued to each
  other are no affiliation (2508.10104), a block LaTeXML cut at its commas and "and"s
  gives no pieces (2411.15633), symbols that follow their affiliations lead none
  (2505.11293) and one symbol's affiliation is never everyone's, markers after wide spaces
  split (2402.13251), and IEEE's template author is no affiliation.
- 10: last, the affiliations a thanks note lists without a sentence around them, IEEE
  conference classes' (2609.26325, 2609.03677), their numbered markers read where LaTeXML
  printed their math as text (2609.16443) (AFF-11).
- 11: a sentence's "is at" or "is with" gives an affiliation only when it is capitalized,
  names an institution, ends with a country or holds a comma ("This work is at the
  intersection of vision and language" gives none), cut at its semicolons; one
  affiliation such sentences give is no longer everyone's, the sentences placing whom they
  name; and the numbered markers of thanks notes anchor authors' markers (2609.03677)
  (AFF-9).
- 12: a run of markers with nothing between them marks the text after them all: version
  11 placed only the last author of "*†‡ Y. Yang and J. Bos are with ..." (2610.13891,
  2610.13872), where version 9 placed both (AFF-33).
- 13: a numbered footnote whose pieces do not all name an institution gives them up to its
  correspondence sentence when they qualify as a thanks note's list, and its markers anchor
  them: ICML's notice, "¹University of Tübingen. ²KAIST AI. Correspondence to: …", gave
  nothing (2610.35857, 2610.35706) (AFF-34).
- 14: markers raised by a span's style are superscripts, and one set apart in spaces before
  a capital starts a numbered line ("¹ NVIDIA ² MIT ³ UCB", one affiliation, 2610.19495);
  lines led by markers that are only notes and names leave the block to its unmarked
  lines, and a row set apart in wide spaces is kept whole when one piece names an
  institution ("Meta AI Research    WRI    Inria", nothing, 2508.10104; "Tencent HY" and
  "UC Merced" beside "Southeast University", 2610.14852); curly double quotes fold in
  names ('Linxi "Jim" Fan') (AFF-37).
- 15: older pages, which ar5iv renders: an address without its country on a line of its own
  completes the affiliation before it ("Zalando Research" / "Mühlenstraße 25, 10243
  Berlin", 1708.07747), a French unit waits for its institution ("Département
  d'informatique …" / "Université de Montréal", 1411.1784), a mailbox list glued to the
  country goes ("Singapore{…}@nus.edu.sg", 1312.4400), and a line break's spacing printed
  as text tells no author field cut at its commas ("[0.25cm]", 2105.15203, which gave
  nothing) (AFF-37).
- 16: lines led by symbols count when half name an institution and the others are no
  sentence nor role ("⋆Facebook AI †Sorbonne University", 2012.12877), a contribution note
  glued to the affiliation after it goes ("Equal senior contributionsDeepMind",
  2204.14198), and an affiliation glued to the last of several names in one creator counts
  ("Jian SunMegvii Technology", 2107.08430) (AFF-37).
- 17: names glued to each other before the glued affiliation are skipped ("Ismail Ben
  AyedJose DolzÉTS Montreal", 2312.12730) (AFF-37).
- 18: a page signed by organizations instead of its listed authors gives them ("Qwen
  Team", "Alibaba Group", 2502.13923), and a row set apart in wide spaces counts with a
  collective ("Qwen Team  Alibaba Group", 2409.12191) (AFF-38).
- 19: an address in typewriter type glued to the word before it is set apart, which the
  contact cleanup took away with it: "University of Oxford" gave "University of"
  (2006.13662), "Adobe Research & HKU" gave "Adobe Research &" (2311.09217) (AFF-37).
- 20: what the review of the archive's re-read found (AFF-40): a name with its marker read as
  text is a name ("Saining Xie 1", 2406.18533), a marker ending a span of text starts the
  line after it (2605.09681), several addresses at the end of a string go together
  (DreamFusion's "Google Research, UC Berkeley", 2209.14988), a "Project:" label goes
  (2406.18522), initials glued to the surname name their author ("Z.Dong", 2410.08613), a
  template's example author gives nothing (2502.10841), a company named after its AI counts
  in a block without markers ("Stability AI", 2311.15127), the listing's dotless i folds
  (2505.12089); and the cleaning: parts glued after a name of several words or a company
  ("Visual Geometry GroupUniversity of OxfordUK", "ByteDance IncShanghai"), ORCID
  identifiers, "now at" and interns' notes, CVPR's "Institution2" go.
- 21: what version 20 cut (AFF-41): an address glued to the word before it took the word
  with it ("Technion - Israel Institute of Technologyauthor@…" gave "… Institute of",
  2006.14610; "Zhejiang Universityauthor@…" gave "Zhejiang", 2011.00147), in any span
  of text too (2412.06141); a string ending in a preposition is cut and goes, one ending in
  "and" keeps what precedes it when that is whole ("The University of Texas at Austin
  and", 2410.14919); "Faculty of 3mE" is no marker (2203.10157); institutions run
  together after a country or another university are set apart (2006.09785, 1904.04514).
- 22: the second audit's (AQ-2, AQ-3, AQ-5, EXT-3): a footnote mark beside markers written by
  hand points to a note, not an affiliation (2609.39548); a numbered affiliation takes the
  lines after it that go on with it, as table rows set them (2609.38607, 2609.33449); one
  block LaTeXML spread over the creators is read as one, everyone at it (2609.13271,
  2609.06726); a mailbox or mail domain without its "@" is a contact detail ("gmail.com").
- 23: one vocabulary each (EXT-7, EXT-4): every marker symbol leads nothing (the asterisk
  operator, "♠", "★ Ropedia"), an institution's word inside an author's name ("Slabaugh") keeps a line of
  names a line of names, names fold "ł" and "ø" as everywhere else; and the cleaning reads
  wherever an affiliation comes from the markers LaTeXML printed as text ("$1$", "$^a$"),
  the format characters and LaTeX's tilde, and drops a note's sentence on its own ("This
  work was done when the author was at Adobe Research").

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
institution, nor a list of them spelled their own way ("Kate Tolstaya, Sarah Tang" for
"Ekaterina Tolstaya"). A part without an institution word names none when it is a street
before its city ("Kifer Rd, Sunnyvale"), a city before its US state or Canadian province
("Pittsburgh, PA 15213"), a note or a link's label ("Equal supervision", "Project
webpage") or a mailbox name, nor does an independent researcher's town (AQ-4); a city
alone ("Seoul, Korea") still names itself, which nothing tells from "IIT Delhi". What `_JUNK_RE` now rejects, in records extracted before it, mostly names
none: `institution_name` has its own narrower `_JUNK_RE` and `_COUNTRY_RE`, and a
department, school or faculty is no institution; a cut-off "Institute of" would name
itself, but none is stored (`make reclean` drops them from day files).

An institution with a ROR id came from ROR (or OpenAlex, in the archive, whose registry
names may have none); one without, from the rules. A name of the rules takes the id its
name has elsewhere, in ROR's answers or the store, when it has a single one (AQ-6):
"University of Hong Kong", 176 times without, was missing from the map; a name of two ids
("Northeastern University", in China and the United States) takes none. `make institutions-again` names stored
institutions again after a change to the rules: registry names are only made canonical
again, the others named again from their affiliation.

`tests/fixtures/institution-names.json` pins what the rules give 3,704 stored strings
(`test_institution_names.py`, EXT-5): a change to them shows there as a diff to review,
written again with `UPDATE_GOLDEN=1`. Without it, all of `_ORGANIZATION_RE` could go with
every test green.

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
