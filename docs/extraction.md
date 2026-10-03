# Affiliations and venues: how they are extracted

The rules behind `sources/arxiv_html.py` (affiliations and who is where), `venue.py` (the
venue of a paper) and their offline re-runs. Every rule here was added for a real page;
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
  cached pages as stored and as extracted today, nothing written) and `make stats`.

## Sources, in order

- `ltx_role_affiliation`/`ltx_role_address` contacts in `div.ltx_authors`.
- `ltx_note` of roles `address` and `institutetext` anywhere, and `footnotetext` notes that
  are direct children of the article and start with a marker.
- Numbered lines after the names.
- "A is with B" sentences in `thanks` notes.

A source that only names authors leaves its turn to the next one: IEEE classes put the
names in the affiliation macro and the affiliations in thanks notes.

## Cleaning

- Several "is with" sentences on one line: each affiliation ends at the last full stop
  before the next sentence, skipping initials ("..., Spain. L. Zhinin is with"), so that
  abbreviations inside it survive ("Dept. of CS, MIT, USA").
- "A and B are with X" gives X wherever it is written, affiliation macros included (unless
  what precedes the verb names an institution). IEEE's "X, China, and also with Y" is
  split: `clean_affiliations` returns every affiliation of one string, and the author gets
  them all (2609.00814).
- Author names printed as affiliations ("Nicolás Ugrinovic", "Yiqun Zhang, and Yiu-Ming
  Cheung", "Benoît Macq Fellow, IEEE") are dropped by `names_only_authors`, which compares
  each name of the list by `name_key`. Strings with an institution word stay, and so do
  collectives that sign as authors ("Alzheimer's Disease Neuroimaging Initiative"). Once
  names were dropped, a single affiliation left is not everyone's: 2609.38180 would
  otherwise put Takaaki Shiratori at CMU.
- Obfuscated addresses ("jane (at) example.org", "lab [at] example.org") and lists of
  mailbox names ("{jane.doe, john.roe}") are stripped, keeping the affiliation they follow.
  `_JUNK_RE` rejects what still passes: lone words ("the", "dot"), link and contribution
  leftovers ("Code", "Core Contributors"), units cut off by a line break ("School of") and
  lone countries. The web's `institutionName` mirrors it (`JUNK_RE`, `COUNTRY_RE`) for
  records extracted before.
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
- Place-only affiliations written as separate contact nodes ("Carnegie Mellon University",
  then "Pittsburgh, PA 15213") are not joined: joining across nodes would also have to
  change every mapping tier.

## Who is where: the author mapping

The mapping reuses the same nodes, in tiers: per-creator contacts, superscript markers
matched with marker-led (or marker-trailed) lines, "A is with B" sentences (in thanks notes
and affiliation contacts: 2609.06721 writes them in the last author's block), plus the
trivial single-affiliation and single-author cases. A wrong pair is worse than none:
ambiguous name alignments drop the whole tier, and unresolved authors stay `null`.

- Links set as authors ("Project Page", a repository) are not creators: 2609.37107
  followed its last author with two, and its shared block went unnoticed.
- After a name, a marker glued to the next word introduces an affiliation line, not the
  name's: "Bob Smith⟨2⟩ ⟨1⟩Stanford University" places Bob at 2 only.
- Per-creator contacts place nobody when only the last creator carries them: LaTeXML
  attaches a block shared by every author to the last one (2609.37098 gave its 7
  affiliations to its 9th author, 2609.00866 its 25 to its 55th).
- A creator naming several people ("A, B and C", "A & B") is left out of the per-creator
  tier: 2609.05583's single creator for six authors is then placed by its markers.

## Institutions (ROR)

`api.ror.org/v2/organizations?affiliation=` marks one match `chosen`. Only those are kept,
and only when one of the organization's names (not an acronym) of at least two words
appears word for word in the affiliation: `chosen` alone matched "ARC Lab, Tencent" to an
association called ARC and "180 Queen's Gate" to "The Gate". ROR names about 65% of the
strings (universities in full); acronyms and companies are named by the web app's own
rules (`web/src/institutions.ts`), which map acronyms to ROR's names so that both merge.
The match also gives the organization's ROR id (`institution_ids`). A failing ROR never
fails a run: lookups stop and resume next run.

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
