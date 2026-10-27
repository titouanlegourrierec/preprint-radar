"""Extract front matter (affiliations, abstract) from arXiv HTML renderings (LaTeXML output).

The HTML front matter depends on the LaTeX class used by the authors. The paper-level set
of affiliations is extracted first (what search and filtering need); when the page also
says who is where — one affiliation block per author, superscript markers, or "A is with
B" notes — each author is additionally mapped to their own affiliations.
"""

import gzip
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from preprint_radar.exceptions import NotFoundError
from preprint_radar.http import HttpClient
from preprint_radar.latex import plain_text

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = 12
"""Version of the extraction heuristics of this module, stored with the affiliations they give.

Bump it with any change that alters what a page gives (affiliations, author mapping), so
that ``reextract`` reads those papers again, from the page cache when it holds them.

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
"""

# LaTeXML renders line breaks and \quad between affiliations as newlines, em spaces
# or runs of (non-breaking) spaces.
_SEPARATOR_RE = re.compile(r"\n|\u2003|\s{2,}")
# Contact details and footnotes that are not affiliations.
_NOISE_RE = re.compile(
    r"@|https?://|www\.|equal(ly)? contribut|contributed equally|correspond|work done|project lead"
    r"|senior author|first author|co-first|joint first|equal advising|internship"
    # Phone numbers and an author's placeholder: "Tel.: +49 ...", "TODO: X's affiliation".
    r"|\btel\.?\s*:|\bfax\s*:|\btodo\b",
    re.IGNORECASE,
)
# The vertical space of a LaTeX line break (\\[5pt]), which LaTeXML prints as text.
_LATEX_SPACE_RE = re.compile(r"\[\s*-?\d*\.?\d+\s*(?:pt|em|ex|mm|cm|in|bp|pc|mu)\s*\]")
# The label of a link whose address is removed as a contact detail, sometimes glued to the
# affiliation before it: "MITProject page".
_LINK_LABEL_RE = re.compile(r"project\s+(?:page|website|homepage|repository|site)\b\s*:?", re.IGNORECASE)
# Contact details after an affiliation: "..., USA. email: {a, b}@nyu.edu", "(e-mail: ...)",
# an address in brackets, which unwrapped thanks notes glue to the sentence: "..., Hong
# Kong SAR, China (author@connect.ust.hk)" (2609.10082), or one that ends the line: "...,
# Vienna, Austria author@technikum-wien.at" (2610.02974), mailboxes included: "...,
# Germany. {pm.wolf, cremers}@tum.de" (2610.03283), the sentence's full stop after it: "...,
# Italy. {name.surname}@unitn.it." (2609.28184). Its label may be glued to the country
# before it: "..., MI, USAEmail:" (2608.29996).
_CONTACT_TAIL_RE = re.compile(
    r"\(?\s*\be-?mails?\b.*$|(?<=[a-z])e-?mails?\s*:.*$|[(\[]\s*[\w.+-]+@.*$"
    r"|\s(?:\{[^{}]*\}|[\w.+-]+)@[\w-]+(?:\.[\w-]+)+\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)
# E-mail addresses written to escape harvesters: "jane (at) example.org", "lab [at] example.org".
_OBFUSCATED_EMAIL_RE = re.compile(
    r"[\w.+-]*\s*[\[(]\s*at\s*[\])]\s*[\w-]+(?:\s*(?:\.|[\[(]\s*dot\s*[\])])\s*[\w-]+)+", re.IGNORECASE
)
# What the data contract keeps out of affiliations, which `validate` refuses: an address,
# a link, an obfuscated "(at)", a list of mailbox names. "@" alone is not one: OpenAlex names
# institutions like "IIT@MIT". A cleaned string still holding one is no affiliation (AFF-32).
_CONTACT_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+|https?://|www\.|[\[(]\s*at\s*[\])]|\{\s*[a-z0-9._+-]+\s*[,;|]",
    re.IGNORECASE,
)
# What is left of a contact detail in brackets: "University of Zurich, Switzerland ()".
_EMPTY_BRACKETS_RE = re.compile(r"\(\s*\)|\[\s*\]")
# Mailbox names whose "@domain" is printed elsewhere: "{jane.doe, john.roe}", sometimes
# unclosed, the list going on in another node, whose affiliation the line join glues on:
# "{pau.rodriguez,ablaas,michal_klein,napostoloff, Apple" (2410.23054). A name is in lower
# case, or capitalized when dots or underscores join its parts ("{Jane.Doe, A.Roe",
# 2610.25235), which the words of an affiliation, after which an unclosed list ends, never are.
_MAILBOX = r"(?:[A-Za-z0-9+-]+(?:[._][A-Za-z0-9+-]+)+|[a-z0-9_.+-]+)"
_MAILBOX_LIST_RE = re.compile(
    rf"\{{\s*{_MAILBOX}(?:\s*[,;|]\s*{_MAILBOX}|\s+{_MAILBOX})+"
    r"\s*(?:[,;]?\s*(?:\}|$)|[,;]\s*(?=[A-Z]))"
)
# The people an IEEE-style affiliation starts with: "The authors are with Delft University",
# "A. Doe and B. Roe are with the University of X", or their role there: "Manoj Karnekar is
# Robotics Lead at FloMobility" (2610.05505). Only what follows is the affiliation.
_SUBJECT_RE = re.compile(
    r"^(?P<subject>\D*?)\b(?:is|are)\s+(?:also\s+|now\s+|currently\s+|additionally\s+)?"
    r"(?:with|at|affiliated\s+with|(?:an?\s+|the\s+)?(?:[\w-]+\s+){1,4}?at)\s+(?:the\s+)?",
    re.IGNORECASE,
)
# IEEE's "X, China, and also with Y": one string, several affiliations.
_ALSO_WITH_RE = re.compile(
    r"[\s,;]*\b(?:and\s+)?(?:(?:is|are)\s+)?also\s+(?:with|at|affiliated\s+with)\s+(?:the\s+)?",
    re.IGNORECASE,
)
# IEEE-style acknowledgment notes: "A. Author and B. Author are with the Department of X".
_IS_WITH_RE = re.compile(
    r"\b(?:is|are)\s+(?:also\s+|now\s+|currently\s+|additionally\s+)?(?:with|at|affiliated\s+with)\s+(?:the\s+)?",
    re.IGNORECASE,
)
# A full stop that ends a sentence, not an initial's: "Spain. L. Zhinin is with" ends at "Spain.".
_FULL_STOP_RE = re.compile(r"(?<!\b[A-Z])\.\s+")
# The same people's next affiliation in one sentence: "is with X and is also with Y".
_TRAILING_CONNECTOR_RE = re.compile(r"[\s,]+(?:and|&)\s*$", re.IGNORECASE)
# Sentences that follow an affiliation in acknowledgment notes.
_NEXT_SENTENCE_STARTS = (
    r"(?:This|These|The\s+work|Corresponding|Manuscript|He|She|They|We|Our|Work|Part|Funding|Supported)\b"
)
_NEXT_SENTENCE_RE = re.compile(rf"\.\s+(?={_NEXT_SENTENCE_STARTS})")
# A line of a note that starts a sentence of its own, or a footnote marker: "* Equal Contribution".
_SENTENCE_START_RE = re.compile(
    rf"\s*(?:{_NEXT_SENTENCE_STARTS}|[*\u2217†‡§¶⋆]|\(?e-?mails?\b)", re.IGNORECASE
)
# Leading footnote markers: "1 Cornell University", "* MIT", "†‡ NVIDIA". Digits that start
# a name are not markers: "54th Research Institute", "3M Company", "3D Vision Lab".
_LEADING_MARKER_RE = re.compile(r"^(?:[\s*†‡§¶⋆,]|\d+(?!\d|(?:st|nd|rd|th|[DKM])\b))+")
# A name that starts with a number: "3M Company", "3D Vision Lab" (numbered "2 3D Vision Lab"),
# or with a lowercase letter before a capital: "eBay" (2610.00812).
_NUMBER_NAME = r"(?![DKM]\b)\s*(?P<name>(?:\d[DKM]\b\s*)?(?:[A-Z]|[a-z](?=[A-Z])).{2,})$"
# A line break, which LaTeXML does not always follow with a newline: "Dept. of Computer
# Science<br>University of Alabama" would read as one affiliation.
_LINE_BREAK_RE = re.compile(r"<br\b[^>]*>", re.IGNORECASE)
# The TeX source LaTeXML keeps beside rendered math: a marker written "$\dagger$" read
# "†\dagger", which no affiliation anchors, and the markers placed nobody (2610.12978).
_ANNOTATION_RE = re.compile(
    r"<annotation(?:-xml)?\b[^>]*>.*?</annotation(?:-xml)?>", re.IGNORECASE | re.DOTALL
)
# Conjunctions left over when a line break splits "A University and B Institute".
_CONNECTOR_RE = re.compile(r"^(?:and|&)(?:\s+|$)", re.IGNORECASE)
# A line that ends like this continues on the next one ("School of Medicine, and").
_CONTINUED_RE = re.compile(r"(?:,|\band|&)\s*$", re.IGNORECASE)
# So does one that ends with a preposition: "Key Laboratory ... of Ministry of" / "Education"
# (2609.11477). Lowercase only: "TU Wien, AT" ends with a country code.
# After a space: "technikum-wien.at" ends an address (2610.02974).
_DANGLING_RE = re.compile(r"(?<=\s)(?:of|for|the|at|in|on|de|du|des|der|für|und)\s*$")
# The connector of a list cut after it: "The University of Hong Kong, and". Not one without
# a comma, which ends a name cut short ("Nanjing University of Posts and").
_LIST_END_RE = re.compile(r"\s*,\s*(?:and|&)$", re.IGNORECASE)
# A LaTeX command LaTeXML printed as text, glued to what follows: "\addrDepartment of ...".
# Its name is lowercase there: the capital starts the affiliation.
_MACRO_RE = re.compile(r"\\(?:[a-z]+(?=[A-Z])|[A-Za-z]+\*?(?:\s+|$))")
# A numbered marker written as text inside a string, glued to the next word: " 2Duke".
_INLINE_MARKER_RE = re.compile(r"(?<=\S\s)\d{1,2}(?=[^\W\d_]{2})")
# A word that starts with such a marker: "2CASIA", "2HKUST(GZ)".
_MARKED_WORD_RE = re.compile(r"\d{1,2}[^\W\d_][^\d\s]*")
# Numbered affiliation lines in free-form author blocks (CVPR-like classes): "1ETH Zurich".
_NUMBERED_LINE_RE = re.compile(r"^\s*\d{1,2}" + _NUMBER_NAME, re.MULTILINE)
# Words of institutions. Not "Foundation Model", a team of Li Auto (2609.21449) and the
# subject of half the papers.
_INSTITUTION_WORD_RE = re.compile(
    r"univ|institut|college|school|lab|cent(?:er|re)|hospital|academy|\binc\b|\bltd\b|gmbh|corp|company"
    r"|research|department|faculty|foundation(?!\s+models?\b)|technolog|polytechn",
    re.IGNORECASE,
)
# Countries, by the names affiliations write them in (AFF-18: "Kazakhstan", "Sri Lanka" and
# "Kenya" were missing). Not those that are also names of people, which a line of names
# would end with (Jordan, Chad, Georgia), nor Wales, which ends "New South Wales".
COUNTRIES = (
    r"USA|U\.S\.A?\.?|United States(?: of America)?|UK|U\.K\.|United Kingdom|England|Scotland"
    r"|Northern Ireland|(?:P\.?\s?R\.?\s?)?China|Hong Kong(?: SAR)?|Macau|Macao|Taiwan|Japan"
    r"|(?:South |Republic of )?Korea|Mongolia|Singapore|India|Sri Lanka|Nepal|Bhutan|Maldives|Pakistan"
    r"|Bangladesh|Afghanistan|Kazakhstan|Uzbekistan|Kyrgyzstan|Tajikistan|Turkmenistan|Azerbaijan|Armenia"
    r"|Vietnam|Viet Nam|Thailand|Malaysia|Indonesia|Philippines|Cambodia|Laos|Myanmar|Brunei"
    r"|Germany|France|Italy|Spain|Portugal|(?:The )?Netherlands|Belgium|Luxembourg|Switzerland|Austria"
    r"|Liechtenstein|Monaco|Andorra|Sweden|Norway|Denmark|Finland|Iceland|Ireland|Poland|Czech Republic"
    r"|Czechia|Slovakia|Slovenia|Croatia|Serbia|Bosnia and Herzegovina|Montenegro|North Macedonia|Albania"
    r"|Kosovo|Bulgaria|Hungary|Romania|Moldova|Greece|Cyprus|Malta|Estonia|Latvia|Lithuania|Belarus"
    r"|Ukraine|Russia(?:n Federation)?|Turkey|Türkiye|Israel|Palestine|Lebanon|Syria|Iraq|Iran|Kuwait"
    r"|Bahrain|Oman|Yemen|Saudi Arabia|United Arab Emirates|UAE|Qatar|Egypt|Libya|Tunisia|Algeria|Morocco"
    r"|Nigeria|Ghana|Senegal|Cameroon|Ethiopia|Kenya|Uganda|Tanzania|Rwanda|Zambia|Zimbabwe|Botswana"
    r"|Namibia|Mozambique|Madagascar|Mauritius|Benin|Burkina Faso|C[ôo]te d'Ivoire|Ivory Coast|Sudan"
    r"|South Africa|Canada|Mexico|Guatemala|Costa Rica|Panama|Cuba|Jamaica|Puerto Rico|Dominican Republic"
    r"|Brazil|Chile|Argentina|Uruguay|Paraguay|Bolivia|Colombia|Venezuela|Peru|Ecuador|Australia"
    r"|New Zealand|Fiji"
)
# A line that ends with a country, as in "Munich, Germany" or "CA 94720, USA".
_COUNTRY_END_RE = re.compile(rf"(?:^|,\s*|\s)(?:{COUNTRIES})\.?$", re.IGNORECASE)
# An affiliation that ends with its country, after a comma: not a name that ends with one,
# like "National Research Council Canada" (2609.12374), which a place in the same country
# still completes.
_ADDRESS_END_RE = re.compile(rf"(?:^|,\s*)(?:{COUNTRIES})\.?$", re.IGNORECASE)
# What passes every other rule without being an affiliation: the leftover of a link label
# or a contribution note ("Code", "Core Contributors"), a unit cut off by a line break
# ("School of"), a lone word ("the", "dot"), or a country alone.
_JUNK_RE = re.compile(
    r"the|an?|and|of|dot|code|github|data(?:set)?|demo|video|website|homepage"
    r"|(?:core\s+|main\s+)?contributors?|(?:co-?)?(?:first|second|last|senior)\s+authors?"
    r"|(?:graduate\s+school|graduate|school|department|faculty|institute|college|laboratory|lab|cent(?:er|re))"
    r"(?:\s+(?:of|for))?"
    # The author of IEEE's template, left in by some (2312.17663).
    r"|ieee\s+publication\s+technology\s+department"
    rf"|(?:{COUNTRIES})\.?",
    re.IGNORECASE,
)
_MAX_PLACE_LENGTH = 60
# The longest piece of an author field cut at its commas that tells the cut: "College Park".
_MAX_PIECE_WORDS = 2
# A unit whose institution is missing: "Department of Computer Science and Engineering".
_BARE_UNIT_RE = re.compile(
    r"(?:the\s+)?(?:department|dept\.?|school|faculty|division|laboratory|lab|cent(?:er|re)|institute)"
    r"\s+(?:of|for)\b",
    re.IGNORECASE,
)
_HOST_RE = re.compile(
    r",|univ|institut|polytechn|academy|college|hospital|\binc\b|\bltd\b|gmbh|corp|company",
    re.IGNORECASE,
)
# Where a footnote marker started a line, while a node's lines are read (never stored).
_MARKER_BREAK = "\ue000"
# Two parts of an affiliation glued where LaTeXML lost a line break (IEEE classes print
# "Dept. of Computer ScienceUniversity of Alabama"): a lowercase letter then a capitalized
# word, or a closing bracket then a word. Only after a unit, so that names stay
# ("AnimSchool", "ByteDance", "McGill"), and never inside brackets ("(ShenZhen)").
_GLUE_RE = re.compile(r"(?<=[a-z]{2})(?=[A-Z][a-z])|(?<=\))(?=[^\W\d_])")
_UNIT_WORD_RE = re.compile(
    r"\b(?:department|dept|school|faculty|division|laborator(?:y|ies)|lab|cent(?:er|re)|institute|college"
    r"|academy|program(?:me)?|thrust|unit)\b",
    re.IGNORECASE,
)
# elsarticle's \affiliation{organization=..., city=..., country=...}, which LaTeXML prints
# verbatim. Any key counts once one of these is present (authors misspell them).
_KEYVAL_RE = re.compile(r"\b(?:organization|addressline|city|postcode|state|country)\s*=", re.IGNORECASE)
_KEY_RE = re.compile(r"\b([a-z]+)\s*=", re.IGNORECASE)
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,;])")
# Empty fields of some LaTeX classes leave commas in a row: "FPT University, , Cantho".
_REPEATED_COMMA_RE = re.compile(r",(?:\s*,)+")
_EDGE_PUNCTUATION = " ,;:."
_MIN_LENGTH = 3

# Superscripts that mark contribution notes rather than affiliations (U+2217 is LaTeX's \ast).
_SYMBOL_MARKERS = frozenset("*\u2217†‡§¶⋆♯♭#°ª")
_SYMBOL_SPLIT_RE = re.compile(f"([{re.escape(''.join(sorted(_SYMBOL_MARKERS)))}])")
# ``⟨marker⟩`` tokens injected in place of superscripts by :func:`_marked_text`.
_MARKED_RE = re.compile(r"⟨([^⟨⟩]*)⟩")
# The markers after a name. One glued to the next word introduces an affiliation line, not
# the name: "Bob Smith⟨2⟩ ⟨1⟩Stanford University" places Bob at 2 only.
_MARKER_RUN_RE = r"((?:\s*⟨[^⟨⟩]*⟩(?![^\W\d_]))+)"
_MARKER_SPLIT_RE = re.compile(r"[,;\s]+")
# A run of markers with nothing between them marks the text that follows them all: "*†‡ Y.
# Yang and J. Bos are with the Department of ..." (2610.13891) places * and ‡ there.
_ANCHOR_RE = re.compile(r"((?:⟨[^⟨⟩]+⟩\s*)+)([^⟨]+)")
_TRAILING_ANCHOR_RE = re.compile(r"([^⟨⟩]+?)\s*⟨([^⟨⟩]+)⟩")
_NUMBERED_ANCHOR_RE = re.compile(r"^\s*(?P<marker>\d{1,2})" + _NUMBER_NAME, re.MULTILINE)
# Separators of several names in one creator: "A, B and C", "A & B".
_SEVERAL_PEOPLE_RE = re.compile(r",|&|\band\b", re.IGNORECASE)
# Between the names of a pair written without a comma: "Zhiyuan Yang & Jiahao Cheng".
_PAIR_RE = re.compile(r"\s+(?:&|and)\s+", re.IGNORECASE)
# IEEE grades and suffixes printed after a name: "Benoît Macq Fellow, IEEE", "Eduil Nascimento Jr.".
_NAME_SUFFIX_RE = re.compile(
    r"\b(?:(?:senior|life|student)\s+)?(?:fellow|member)\s*,?\s*IEEE\b|\bIEEE\s+(?:senior\s+)?(?:fellow|member)\b"
    r"|\b(?:jr|sr)\b\.?",
    re.IGNORECASE,
)
# A collective that signs a paper is its own affiliation: "Alzheimer's Disease Neuroimaging Initiative".
_COLLECTIVE_RE = re.compile(r"\b(?:initiative|consortium|collaboration|team|group)\b", re.IGNORECASE)
# "The authors are with X", "All authors are with X": everyone is there.
_ALL_AUTHORS_RE = re.compile(r"\b(?:the|all(?:\s+the)?)\s+authors\b")
# Sentence ends, except after an initial ("E. Milara") or an acronym ("USA.").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[^\sA-Z][.;])\s+")
# Notes holding affiliations, wherever they are: address and institute macros, and
# affiliation notes, where Taylor & Francis' class lists its lettered affiliations after
# the abstract (2610.15403).
_AFFILIATION_NOTES = (
    ".ltx_note.ltx_role_address, .ltx_note.ltx_role_institutetext, .ltx_note.ltx_role_affiliation"
)
# Free-form lines led by symbol markers: "*Oregon State University †The Ohio State
# University" (2610.17605). Symbols mark notes too ("*Equal contribution"): see
# :func:`_symbol_affiliations`.
_SYMBOL_LINE_RE = re.compile(
    rf"^\s*(?P<marker>[{re.escape(''.join(sorted(_SYMBOL_MARKERS)))}]+)" + _NUMBER_NAME, re.MULTILINE
)

# Thanks notes LaTeXML types as saying who funded the work, or whom to write to.
_OTHER_THANKS = frozenset({"ltx_thanks_funding", "ltx_thanks_correspondence"})
# A numbered marker LaTeXML printed as text, its math unparsed: "$^1$University of Southern
# California, $^2$Stanford University" (2609.16443, whose ^ is U+02C6, the modifier letter
# circumflex), "$^{2}$".
_TEXT_MARKER_RE = re.compile(r"\$\s*[\^\u02c6]\s*\{?\s*(\d{1,2})\s*\}?\s*\$")
# What a sentence of a thanks note says, and a list of affiliations does not: "Work done
# while A was a visiting student", "This work was supported by the X Foundation", "Now at".
_SENTENCE_WORD_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|has|have|had|work(?:ed|s)?|done|while|supported|funded"
    r"|grants?|projects?|contribut\w*|correspond\w*|equal\w*|e-?mail|thanks?|acknowledg\w*"
    r"|submitted|accepted|published|copyright|now)\b",
    re.IGNORECASE,
)
# A web domain alone, whose "lab" is no laboratory: "jzlab.org" (2610.00751).
_DOMAIN_RE = re.compile(r"[\w-]+(?:\.[\w-]+)+")

type AuthorAffiliations = tuple[tuple[int, ...] | None, ...]
"""Per author, the indices of their affiliations; ``None`` when unknown for that author."""


@dataclass(frozen=True, slots=True)
class FrontMatter:
    """Information extracted from the first page of a paper.

    Attributes:
        affiliations: Distinct affiliations, in order of first appearance (possibly empty).
        abstract: Abstract with math as ``$LaTeX$``, or ``None`` if not found.
        author_affiliations: For each author given to the parser, the indices of their own
            affiliations in ``affiliations``; ``None`` for an author the page does not
            place, and ``None`` altogether when the page never says who is where.
    """

    affiliations: tuple[str, ...] = ()
    abstract: str | None = None
    author_affiliations: AuthorAffiliations | None = None


class PageCache:
    """The front matter of every HTML page read, so that extracting again reads no page.

    One gzipped file per paper version (``<directory>/2609/2609.30249v1.html.gz``), holding
    :func:`front_matter_html` of the page: 1 or 2 KB instead of hundreds. A new version of
    a paper is a new page, read again. A page that does not exist (404) leaves an empty
    ``.missing`` file instead, which the archive's pages skip (:meth:`missing`).
    """

    def __init__(self, directory: Path) -> None:
        """Keep the pages in ``directory`` (created on first write)."""
        self.directory = directory

    def __contains__(self, html_url: object) -> bool:
        """Whether the cache holds the page at ``html_url``."""
        path = self._path(html_url) if isinstance(html_url, str) else None
        return path is not None and path.is_file()

    def get(self, html_url: str) -> str | None:
        """The cached front matter of the page at ``html_url``, if any."""
        path = self._path(html_url)
        if path is None or not path.is_file():
            return None
        return gzip.decompress(path.read_bytes()).decode("utf-8")

    def put(self, html_url: str, html: str) -> None:
        """Keep the front matter of the page at ``html_url``, whose HTML is ``html``.

        Args:
            html_url: URL of the paper's HTML rendering, which names the cached file.
            html: The page's HTML, of which only the front matter is kept.
        """
        path = self._path(html_url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written aside then renamed, so that a killed run never leaves a truncated page.
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(gzip.compress(front_matter_html(html).encode("utf-8"), mtime=0))
        tmp.replace(path)

    def missing(self, html_url: str) -> bool:
        """Whether arXiv answered that the page at ``html_url`` does not exist (:meth:`put_missing`)."""
        path = self._path(html_url)
        return path is not None and path.with_suffix(".missing").is_file()

    def put_missing(self, html_url: str) -> None:
        """Remember that the page at ``html_url`` does not exist: arXiv could not render it."""
        path = self._path(html_url)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.with_suffix(".missing").touch()

    def stale(self, html_url: str) -> bool:
        """Whether the page at ``html_url`` was kept with less than its front matter.

        Kept before the front matter kept its tables, a page lost those of its author block,
        which some classes lay names and affiliations out in (2609.06629); kept before a list
        of acronyms set before the title was skipped, it lost everything (2610.09677). Read
        again, either may give fewer affiliations than the page has.
        """
        html = self.get(html_url)
        # A page without a document was kept whole, and lost nothing.
        return (
            html is not None
            and "ltx_document" in html
            and (_FRONT_MATTER_MARK not in html or _EMPTY_FRONT_MATTER_RE.search(html) is not None)
        )

    def discard(self, html_url: str) -> None:
        """Forget the page at ``html_url``, so that it is downloaded again next time."""
        path = self._path(html_url)
        if path is not None:
            path.unlink(missing_ok=True)

    def _path(self, html_url: str) -> Path | None:
        """``<directory>/<yymm>/<id>v<version>.html.gz``; ``None`` for a URL that names no paper version."""
        match = _CACHE_KEY_RE.search(html_url)
        return None if match is None else self.directory / match["month"] / f"{match[0]}.html.gz"


ARXIV_HTML_URL = "https://arxiv.org/html"
_NEW_STYLE_ID_RE = re.compile(r"\d{4}\.\d{4,5}")
# The month of the first papers arXiv rendered in HTML.
_FIRST_RENDERED_MONTH = "2312"
_CACHE_KEY_RE = re.compile(r"(?P<month>\d{4})\.\d{4,5}v\d+$")
# What follows the front matter in a LaTeXML document: the body, references and appendices.
_BODY_CLASSES = frozenset({"ltx_section", "ltx_bibliography", "ltx_appendix"})
# Sections a document may set before its title: a list of acronyms or a glossary
# (2610.09677, 2610.11653), not the body the front matter ends at.
_PREAMBLE_CLASSES = frozenset({"ltx_glossary"})
# Figures and tables say nothing of affiliations, and are most of a front matter's size;
# but for the tables of the author block.
_FIGURE_TAGS = ("figure", "img", "svg", "table")
_FIGURE_CLASSES = frozenset({"ltx_figure", "ltx_table"})
# What a front matter that kept the tables of its author block says of itself.
_FRONT_MATTER_MARK = 'data-front-matter="2"'
# A front matter that kept nothing: every document has a title at least.
_EMPTY_FRONT_MATTER_RE = re.compile(rf"{_FRONT_MATTER_MARK}>\s*</article>")


def front_matter_html(html: str) -> str:
    """The part of an HTML rendering that :func:`parse_front_matter` reads, as a page.

    The children of the document before its first section (title, author block and its
    notes, footnotes, abstract), without figures or tables: what the cache keeps. The
    tables of the author block stay: some classes lay names and affiliations out in one
    (2609.06629, whose five affiliations a cached page had lost). A list of acronyms set
    before the title is no first section: the pages of 2610.09677 and 2610.11653 were kept
    empty, and read again from the cache, lost their affiliations.
    """
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article.ltx_document")
    if article is None:
        return html
    kept: list[str] = []
    for child in article.children:
        if isinstance(child, Tag):
            classes = set(child.get_attribute_list("class"))
            if _PREAMBLE_CLASSES & classes:
                continue
            if child.name == "section" or _BODY_CLASSES & classes:
                break
            if child.name in _FIGURE_TAGS or _FIGURE_CLASSES & classes:
                continue
            for noise in child.select(", ".join([*_FIGURE_TAGS, *(f".{name}" for name in _FIGURE_CLASSES)])):
                if noise.name != "table" or noise.find_parent(class_="ltx_authors") is None:
                    noise.decompose()
        kept.append(str(child))
    article_tag = f'<article class="ltx_document" {_FRONT_MATTER_MARK}>'
    return f"<html><body>{article_tag}{''.join(kept)}</article></body></html>"


def first_version_url(arxiv_id: str) -> str | None:
    """The HTML rendering of a paper's first version, ``None`` before arXiv rendered any.

    arXiv renders the papers submitted since December 2023 (``2312.*``): the first version
    is the one a day file links to for a new paper. Older ones have no rendering, nor have
    old-style identifiers ("cs/0112017").
    """
    if not _NEW_STYLE_ID_RE.fullmatch(arxiv_id) or arxiv_id < _FIRST_RENDERED_MONTH:
        return None
    return f"{ARXIV_HTML_URL}/{arxiv_id}v1"


def fetch_front_matter(
    client: HttpClient, html_url: str, *, authors: Sequence[str] = (), cache: PageCache | None = None
) -> FrontMatter:
    """Download an HTML rendering, or take it from the cache, and extract its front matter.

    Args:
        client: HTTP client, rate-limited according to arxiv.org's crawl delay.
        html_url: URL of the paper's HTML rendering.
        authors: Author names, never reported as affiliations.
        cache: Pages read before; a page downloaded is added to it.

    Returns:
        The front matter; empty if the rendering does not exist.

    Raises:
        FetchError: If the page cannot be retrieved for a reason other than a 404.
    """
    html = cache.get(html_url) if cache is not None else None
    if html is None:
        try:
            html = client.get_text(html_url)
        except NotFoundError:
            logger.info("No HTML rendering at %s", html_url)
            if cache is not None:
                cache.put_missing(html_url)
            return FrontMatter()
        if cache is not None:
            cache.put(html_url, html)
    return parse_front_matter(html, authors=authors)


def parse_front_matter(html: str, *, authors: Sequence[str] = ()) -> FrontMatter:
    """Extract affiliations, abstract and the author-affiliation mapping from a rendering.

    Contact details (e-mails, URLs) are discarded from affiliations so they are never
    republished.

    Args:
        html: Raw HTML of the paper.
        authors: Author names, in the paper's order. They anchor the author-affiliation
            mapping, and names are never reported as affiliations (see
            :func:`names_only_authors`).

    Returns:
        The front matter.
    """
    html = _ANNOTATION_RE.sub("", _LINE_BREAK_RE.sub("\n", html))
    soup = BeautifulSoup(html, "html.parser")
    affiliations, partial = _affiliations(soup, authors)
    return FrontMatter(
        affiliations=affiliations,
        abstract=_abstract(soup),
        author_affiliations=_author_affiliations(html, tuple(authors), affiliations, partial=partial),
    )


def _abstract(soup: BeautifulSoup) -> str | None:
    node = soup.select_one("div.ltx_abstract")
    if node is None:
        return None
    for title in node.select(".ltx_title"):
        title.decompose()
    # Render MathML the way arXiv metadata does, as inline LaTeX, then as plain text.
    for math in node.select("math[alttext]"):
        math.replace_with(f"${math['alttext']}$")
    return plain_text(node.get_text()) or None


def _affiliations(soup: BeautifulSoup, authors: Sequence[str]) -> tuple[tuple[str, ...], bool]:
    """Distinct affiliations of the front matter, and whether its source left some lines out.

    Lines left out are author names dropped from the affiliations, or lines of a block
    without markers that may be other affiliations: either way, one affiliation left is not
    everyone's (:func:`_author_affiliations`).

    Sources, from the most to the least reliable: affiliations and addresses marked up in
    the author block (with the numbered lines LaTeXML set as authors beside them, and the
    affiliations glued to a name), front-matter notes (from the LaTeX address, institute,
    affiliation and numbered footnotetext macros), numbered lines after the author names,
    lines led by symbols that each name an institution, "A is with B" sentences in thanks
    notes, the lines of a block without markers that name an institution, and last the
    affiliations a thanks note lists without a sentence (:func:`_listed_affiliations`). The
    first source that gives an affiliation is used; one that only names authors gives none:
    IEEE classes put the names in the affiliation macro and the affiliations in thanks
    notes. Affiliations are deduplicated case-insensitively.
    """
    article = soup.select_one("article.ltx_document") or soup
    # Notes are read first: the author block is then cleaned of them.
    from_notes = [segment for note in soup.select(_AFFILIATION_NOTES) for segment in _note_segments(note)]
    from_notes += [
        segment
        for note in article.find_all("span", class_="ltx_role_footnotetext", recursive=False)
        for segment in _footnote_affiliations(note)
    ]
    thanks_notes = soup.select(".ltx_note.ltx_role_thanks")
    thanks = [_note_text(note) for note in thanks_notes]
    listing = [
        text
        for note, text in zip(thanks_notes, thanks, strict=True)
        if not _OTHER_THANKS & set(note.get_attribute_list("class"))
    ]

    tagged: list[str] = []
    numbered: list[str] = []
    symbols: list[str] = []
    unmarked: list[str] = []
    unmarked_partial = False
    block = soup.select_one("div.ltx_authors")
    if block is not None:
        for noise in block.select(".ltx_role_email, .ltx_contact_name, .ltx_note, a"):
            noise.decompose()
        tagged = _tagged_affiliations(block, authors)
        if tagged:
            tagged += _numbered_creators(block)
        else:
            numbered = _numbered_affiliations(block)
            symbols = _symbol_affiliations(block)
            unmarked, unmarked_partial = _unmarked_affiliations(block, authors)
        tagged += _glued_affiliations(block, authors)
    sources = (
        (tagged + from_notes, False),
        (numbered, False),
        # A symbol marks some of the authors, never all of them.
        (symbols, True),
        # The people a sentence names are where it says, not everyone (AFF-9).
        (_stated_affiliations(thanks), True),
        (unmarked, unmarked_partial),
        (_listed_affiliations(listing), False),
    )
    names_dropped = False
    for source, partial in sources:
        found = _dedupe(source)
        affiliations = tuple(
            affiliation for affiliation in found if not names_only_authors(affiliation, authors)
        )
        names_dropped = names_dropped or len(affiliations) < len(found)
        if affiliations:
            return affiliations, names_dropped or partial
    return (), names_dropped


def _tagged_affiliations(block: Tag, authors: Sequence[str]) -> list[str]:
    """Affiliations marked up by LaTeXML: affiliation and address macros of ACM- or IEEE-like classes."""
    return [segment for nodes in _contact_groups(block) for segment in _contact_segments(nodes, authors)]


def _contact_groups(authors: Tag) -> list[list[Tag]]:
    """The affiliation and address nodes of an author block, those of each author together.

    IEEE conference classes write each line of an author's address as its own node:
    "Department of Computer Science", "Dartmouth College", "Hanover, NH, USA" (2609.38705).
    """
    groups: list[list[Tag]] = []
    owners: list[Tag | None] = []
    for node in authors.select(".ltx_role_affiliation, .ltx_role_address"):
        owner = node.find_parent("span", class_="ltx_creator")
        if groups and owner is not None and owners[-1] is owner:
            groups[-1].append(node)
        else:
            groups.append([node])
            owners.append(owner)
    return groups


def _contact_segments(nodes: Iterable[Tag], authors: Sequence[str]) -> list[str]:
    """The affiliations in one author's contact nodes, read as the lines of one text."""
    return _joined((line for node in nodes for line in _lines(node)), authors)


def _numbered_creators(block: Tag) -> list[str]:
    """The numbered affiliation lines LaTeXML set as authors, beside contact nodes.

    2610.12978 gives "¹Sun Yat-sen University" as a contact of its last author, then
    "²Alibaba Group", "³The University of Hong Kong" and "⁴Shanghai Jiao Tong University"
    as creators of their own, each name starting with its number.
    """
    return [
        segment
        for name in block.select("span.ltx_creator.ltx_role_author .ltx_personname")
        if (marker := _leading_marker(name)) is not None and marker.get_text().strip().isdigit()
        for segment in _segments(_pruned(name))
    ]


def _leading_marker(name: Tag) -> Tag | None:
    """The superscript a creator's name starts with: a line of notes or affiliations, no name."""
    first = next((child for child in name.children if not str(child).isspace()), None)
    return first if isinstance(first, Tag) and first.name == "sup" else None


def _glued_affiliations(block: Tag, authors: Sequence[str]) -> list[str]:
    """The affiliations LaTeXML glued to their author's name (:func:`_glued_name`)."""
    return [
        glued[1]
        for name in block.select("span.ltx_creator.ltx_role_author .ltx_personname")
        if (glued := _glued_name(_plain_text(name), authors)) is not None
    ]


def _glued_name(name: str, authors: Sequence[str]) -> tuple[str, str] | None:
    """The author a creator's name starts with, and the affiliation glued to it.

    Some IEEE conference blocks lose every line break of an author's address, the one after
    the name included: "Xiaoya TangScientific Computing and Imaging InstituteUniversity of
    Utah" (2610.17412), and "Tolga Tasdizen*Scientific..." once its marker is dropped. Only
    a listed name followed by a capital, without a space, counts, and never before another
    author's: LaTeXML glues names to each other too, "Huy V. VoMaximilian SeitzerFederico
    Baldassarre..." (2508.10104).
    """
    for author in authors:
        rest = name[len(author) :]
        if (
            rest[:1].isupper()
            and _fold(name[: len(author)]) == _fold(author)
            and not any(_fold(other) in _fold(rest) for other in authors if other != author)
        ):
            return author, rest
    return None


def _symbol_affiliations(block: Tag) -> list[str]:
    """Affiliation lines led by symbol markers in a free-form block: "*Oregon State University".

    2610.17605 marks its four affiliations "*", "†", "‡" and "§". Symbols mark notes too
    ("*Equal contribution", "†Now at Google"): the lines count only when each one that is
    not noise names an institution, as numbered footnotes must (:func:`_footnote_affiliations`).
    Nor when one ends with a symbol: the block's markers follow their affiliations, and
    "Independent§University of Waterloo¶" is not "University of Waterloo" marked "§"
    (2505.11293).
    """
    lines = [match["name"].strip() for match in _SYMBOL_LINE_RE.finditer(_numbered_text(block))]
    kept = [line for line in lines if not _NOISE_RE.search(line)]
    if any(line.endswith(tuple(_SYMBOL_MARKERS)) for line in lines):
        return []
    return kept if all(_INSTITUTION_WORD_RE.search(line) for line in kept) else []


def _unmarked_affiliations(block: Tag, authors: Sequence[str]) -> tuple[list[str], bool]:
    """The lines of a block without contacts nor markers that name an institution: the last source.

    2610.18323 writes its ten names in the rows of a table, then "Xi'an Jiaotong University"
    and an address, without any marker. Any line of a block could pass: only those with an
    institution word or ending with a country count ("United Imaging Intelligence, Boston,
    MA, USA", 2610.02343), joined as :func:`_joined` joins lines, and never one holding an
    author's name (a name LaTeXML glued to its affiliation). A block with lines led by
    markers is read by them alone, and so is a block :func:`_split_at_commas`.

    Returns:
        The affiliations, and whether lines that may be others were left out ("Tencent
        HY", "HKUST(GZ)"): the one affiliation of such a block is everyone's only when
        nothing but names and noise is left.
    """
    marked = _numbered_text(block)
    if _NUMBERED_LINE_RE.search(marked) or _SYMBOL_LINE_RE.search(marked) or _split_at_commas(block, authors):
        return [], False
    copy = _pruned(block)
    for sup in copy.select("sup"):
        sup.decompose()
    text = _LATEX_SPACE_RE.sub("\n", copy.get_text().replace("\xa0", " "))
    lines = [_Line(line.strip()) for line in _SEPARATOR_RE.split(text) if line.strip()]
    names = [_fold(author) for author in authors]
    kept: list[str] = []
    left_out = False
    for line in _joined(lines, authors):
        # Without the authors' names, whose words may hold an institution's ("Labussière").
        rest = _fold(line)
        held = [name for name in names if name in rest]
        for name in held:
            rest = rest.replace(name, " ")
        named = _INSTITUTION_WORD_RE.search(rest) or _ADDRESS_END_RE.search(rest.rstrip(_EDGE_PUNCTUATION))
        if held:
            left_out = left_out or bool(named)
        elif named:
            kept.append(line)
        elif not names_only_authors(line, authors) and clean_affiliations(line):
            left_out = True
    return kept, left_out


def _split_at_commas(block: Tag, authors: Sequence[str]) -> bool:
    """Whether LaTeXML cut the author field at each comma and "and", affiliations included.

    Each piece is then a creator: "University of Science" and "Technology of China", "School
    of Software", "Tsinghua University", "Beijing", "China" (2411.15633, 2510.11387), whose
    lines are pieces rather than affiliations. A creator naming no author that holds a line
    of at most two words naming no institution nor country ("College Park", "Computer
    Engineering", "Telecommunications") tells it.
    """
    names = [_fold(author) for author in authors]
    for name in block.select("span.ltx_creator.ltx_role_author .ltx_personname"):
        text = _plain_text(_pruned(name))
        if any(author in _fold(text) for author in names):
            continue
        for line in _SEPARATOR_RE.split(name.get_text().replace("\xa0", " ")):
            piece = line.strip(_EDGE_PUNCTUATION)
            # A qualifier in brackets is no piece: "(Guangzhou)" under its university (2609.33258).
            if (
                piece
                and not piece.startswith("(")
                and len(piece.split()) <= _MAX_PIECE_WORDS
                and not _NOISE_RE.search(piece)
                and not _INSTITUTION_WORD_RE.search(piece)
                and not _ADDRESS_END_RE.search(piece)
            ):
                return True
    return False


def _note_segments(note: Tag) -> list[str]:
    """Affiliations in an address or institute note, e.g. "⋆The University of Tokyo †NII"."""
    content = note.select_one(".ltx_note_content")
    if content is None:
        return []
    for noise in content.select(".ltx_note, .ltx_note_mark, .ltx_note_type"):
        noise.decompose()
    return _segments(content)


def _footnote_affiliations(note: Tag) -> list[str]:
    """Numbered affiliations in a footnote next to the author list, e.g. "¹School of AI, Wuhan University".

    Only footnotes that start with a marker and consist of institutions qualify, as other
    footnotes of the front matter say anything ("This work has been submitted to...").
    """
    content = note.select_one(".ltx_note_content")
    if content is None:
        return []
    for noise in content.select(".ltx_note_mark, .ltx_note_type"):
        noise.decompose()
    first = next((child for child in content.children if not str(child).isspace()), None)
    if not isinstance(first, Tag) or first.name != "sup":
        return []
    segments = _segments(content)
    return segments if all(_INSTITUTION_WORD_RE.search(segment) for segment in segments) else []


def _note_text(note: Tag) -> str:
    content = note.select_one(".ltx_note_content") or note
    for noise in content.select(".ltx_note_mark, .ltx_note_type"):
        noise.decompose()
    return _unwrapped(content.get_text())


def _unwrapped(text: str) -> str:
    """The text with the lines its source wrapped joined again.

    Thanks notes keep the line breaks of the LaTeX source, which wrap sentences anywhere:
    "are with the School of" then "Intelligent Engineering and Automation" (2609.33097).
    A line continues the previous one unless that one ends a sentence, or the line starts
    one: a sentence of the usual notes, a marker, or a new "B is with" statement, unless
    the previous line holds the start of its list of people (2609.15562).
    """
    lines: list[str] = []
    for line in text.splitlines():
        if (
            lines
            and line.strip()
            and not lines[-1].rstrip().endswith((".", ";", ":", "!", "?"))
            and not (_IS_WITH_RE.search(line) and _IS_WITH_RE.search(lines[-1]))
            and not _SENTENCE_START_RE.match(line)
        ):
            lines[-1] = f"{lines[-1].rstrip()} {line.strip()}"
        else:
            lines.append(line)
    return "\n".join(lines)


def _stated_affiliations(notes: list[str]) -> list[str]:
    """Affiliations stated in sentences: "A and B are with the X, Y (e-mail: ...)".

    Thanks notes are written that way, and so are some affiliation macros, several
    sentences in a row: "A, B and C are at X. A is with Y. B is with Z". What follows "is
    at" or "is with" is cut at its semicolons, and each piece kept only when it is a name
    (:func:`_names_a_place`, AFF-9): "This work is at the intersection of vision and
    language" states none.
    """
    affiliations: list[str] = []
    for line in (line for note in notes for line in note.splitlines()):
        matches = list(_IS_WITH_RE.finditer(line))
        for index, match in enumerate(matches):
            if index + 1 < len(matches):
                # Stop at the sentence that introduces the next people: "..., Spain. C. Li is with".
                text = line[match.end() : matches[index + 1].start()]
                if stops := list(_FULL_STOP_RE.finditer(text)):
                    text = text[: stops[-1].start()]
                else:
                    text = _TRAILING_CONNECTOR_RE.sub("", text)
            else:
                text = line[match.end() :]
            stated = _NEXT_SENTENCE_RE.split(_CONTACT_TAIL_RE.sub("", text), maxsplit=1)[0]
            affiliations += [piece for piece in stated.split(";") if _names_a_place(piece)]
    return affiliations


def _names_a_place(text: str) -> bool:
    """Whether a stated affiliation is a name, not "the intersection of vision and language".

    Capitalized ("MIT", "NVIDIA", "ETH Zurich"), or naming an institution, ending with a
    country or holding a comma, as "the department of physics, ..." does.
    """
    text = text.strip().rstrip(".")
    return bool(
        text[:1].isupper() or _INSTITUTION_WORD_RE.search(text) or _ADDRESS_END_RE.search(text) or "," in text
    )


def _listed_affiliations(notes: list[str]) -> list[str]:
    """The affiliations a thanks note lists without a sentence around them: the last source.

    IEEE conference classes, which IROS papers use, put the affiliations in thanks notes:
    as "A is with B" sentences (:func:`_stated_affiliations`), or alone, the whole note
    ("Department of Computer Science, University of Freiburg, Germany.", 2609.26325), a
    note each, numbered ("¹FZI Research Center for Information Technology, 76131
    Karlsruhe, Germany.", 2609.03677), or a numbered list after other sentences, whose
    markers LaTeXML printed as text ("$^1$University of Southern California, $^2$Stanford
    University", 2609.16443). A note qualifies when none of its pieces reads as a sentence
    or is a web domain, and at least half of them name an institution or end with a
    country: "UC San Diego" names none. Notes on funding and correspondence never do.
    Last, so that it only ever fills an empty page: of 166 thanks notes of 401 cached
    pages (2026-10-17), it read the 4 of these 3 papers, and a domain.
    """
    affiliations: list[str] = []
    for note in notes:
        pieces = marked_pieces(" ".join(_TEXT_MARKER_RE.sub(r" \1", note).split()))
        if len(pieces) > 1 and not pieces[0][:1].isdigit():
            # The sentences before a numbered list.
            pieces = pieces[1:]
        pieces = [stripped for piece in pieces if (stripped := piece.strip(" ,;."))]
        if not pieces or any(
            _SENTENCE_WORD_RE.search(piece) or _DOMAIN_RE.fullmatch(piece) for piece in pieces
        ):
            continue
        named = [
            piece for piece in pieces if _INSTITUTION_WORD_RE.search(piece) or _ADDRESS_END_RE.search(piece)
        ]
        if 2 * len(named) >= len(pieces):
            affiliations += pieces
    return affiliations


def _segments(node: Tag) -> list[str]:
    """Candidate affiliations in a node: one per line, footnote marker or wide space.

    elsarticle's ``key=value`` affiliations ignore line breaks: see :func:`_keyval_chunks`.
    Other lines are joined as :func:`_joined` says.
    """
    return _joined(_lines(node))


@dataclass(frozen=True, slots=True)
class _Line:
    """A line of a node, and whether a footnote marker starts it (a new affiliation)."""

    text: str
    marked: bool = False


def _lines(node: Tag) -> list[_Line]:
    """The lines of a node, split at line breaks, footnote markers and wide spaces."""
    for marker in node.select("sup"):
        marker.replace_with(marker.get_text() if _inside_word(marker) else f"\n{_MARKER_BREAK}")
    text = _LATEX_SPACE_RE.sub("\n", node.get_text().replace("\xa0", " "))
    if _KEYVAL_RE.search(text):
        return [_Line(chunk, marked=True) for chunk in _keyval_chunks(text.replace(_MARKER_BREAK, ""))]
    lines = [line.strip() for line in _SEPARATOR_RE.split(text)]
    return [
        _Line(line.lstrip(_MARKER_BREAK).strip(), marked=line.startswith(_MARKER_BREAK))
        for line in lines
        if line.lstrip(_MARKER_BREAK).strip()
    ]


def _joined(lines: Iterable[_Line], authors: Sequence[str] = ()) -> list[str]:
    """Lines joined into affiliations.

    A line ending with a comma, "and" or a preposition ("Ministry of") continues on the next
    one, unless a marker starts it, so does the name of a
    unit on a line starting with "and" ("Faculty of Medicine" then "and Health Sciences",
    2610.03290), and a line that completes the previous one (:func:`_completes`) is added
    to it after a comma. A line that only names authors is left alone: "Terrence Chen,
    Ziyan Wu" then "United Imaging Intelligence, Boston MA, USA" are names and an
    affiliation (2610.02382), and the names are dropped later.
    """
    joined: list[str] = []
    for line in lines:
        previous = joined[-1] if joined else ""
        if not previous or names_only_authors(previous, authors):
            joined.append(line.text)
        elif (
            _CONTINUED_RE.search(previous)
            or (not line.marked and _DANGLING_RE.search(previous))
            or _continues(previous, line)
        ):
            joined[-1] = f"{previous} {line.text}"
        elif _completes(previous, line):
            joined[-1] = f"{previous.rstrip(_EDGE_PUNCTUATION)}, {line.text}"
        else:
            joined.append(line.text)
    return joined


def _continues(previous: str, line: _Line) -> bool:
    """Whether a line starting with "and" goes on with the unit that ends the previous one.

    "and Statistics" ends "School of Mathematics", but "and Mila" is not part of "Stanford
    University", nor "& Canada-CIFAR AI Chair" of anything.
    """
    return (
        not line.marked
        and line.text.startswith("and ")
        and is_bare_unit(previous.rsplit(",", maxsplit=1)[-1].strip())
    )


def _completes(previous: str, line: _Line) -> bool:
    """Whether a line completes the affiliation before it.

    A line that only names a place ("Munich, Germany") completes one without a country, or
    a name that ends with the place's country: "National Research Council Canada" then
    "London, ON, Canada" (2609.12374), but not "University of Luxembourg" then "Trier,
    Germany", the next column of a table (2609.06629). A
    unit without its institution is completed by the next line, unless a marker starts
    that line or it is not an affiliation: "Department of Computer Science", then
    "Dartmouth College" (AFF-10, 2609.38705).
    """
    if is_place(line.text):
        previous = previous.rstrip(_EDGE_PUNCTUATION)
        if _ADDRESS_END_RE.search(previous):
            return False
        named = _COUNTRY_END_RE.search(previous)
        return named is None or _last_word(named[0]) == _last_word(line.text)
    return (
        not line.marked
        and is_bare_unit(previous)
        and not is_bare_unit(line.text)
        and not _NOISE_RE.search(line.text)
        and clean_affiliation(line.text) is not None
    )


def _last_word(text: str) -> str:
    return text.rstrip(_EDGE_PUNCTUATION).rsplit(maxsplit=1)[-1].casefold()


def is_bare_unit(line: str) -> bool:
    """Whether a line names a unit without its institution, like "Department of Computer Science".

    Args:
        line: A line of an author block, or a stored affiliation.

    Returns:
        ``True`` when it starts with a unit ("School of", "Laboratory for") and has
        neither an institution word nor a comma, after which one usually comes.
    """
    return _BARE_UNIT_RE.match(line) is not None and _HOST_RE.search(line) is None


def is_place(line: str) -> bool:
    """Whether a line only names a place, like "Munich, Germany" or "CA 94720, USA".

    Args:
        line: A line of an author block, or a stored affiliation.

    Returns:
        ``True`` for a short line that ends with a country and has no institution word.
    """
    place = line.strip(_EDGE_PUNCTUATION)
    return (
        len(place) <= _MAX_PLACE_LENGTH
        and not _INSTITUTION_WORD_RE.search(place)
        and _COUNTRY_END_RE.search(place) is not None
    )


def _keyval_chunks(text: str) -> list[str]:
    """Split elsarticle ``key=value`` text into one raw chunk per affiliation.

    Values wrap across lines ("organization=Centre for Human-Computer", then
    "Interaction, ..."), so line breaks are ignored; a key seen again starts the next
    affiliation. The keys are removed later, by :func:`clean_affiliation`.
    """
    flat = " ".join(text.split())
    chunks: list[str] = []
    seen: set[str] = set()
    start = 0
    for match in _KEY_RE.finditer(flat):
        key = match.group(1).casefold()
        if key in seen:
            chunks.append(flat[start : match.start()])
            seen.clear()
            start = match.start()
        seen.add(key)
    chunks.append(flat[start:])
    return [chunk.strip(_EDGE_PUNCTUATION) for chunk in chunks if chunk.strip(_EDGE_PUNCTUATION)]


def _keyval_text(text: str) -> str:
    """One elsarticle affiliation as plain text: its values, the organization first.

    The organization leads so that the institution comes first whatever the order of the
    source. Empty values and separators (``citysep=,``) are dropped, and a value that
    repeats the previous one is kept once (``addressline=Mandi, city=Mandi``).
    """
    parts = _KEY_RE.split(text)
    pairs = [(key.casefold(), value) for key, value in zip(parts[1::2], parts[2::2], strict=True)]
    fields = [parts[0]]
    fields += [value for key, value in pairs if key == "organization"]
    fields += [value for key, value in pairs if key != "organization"]
    kept: list[str] = []
    for field in (field.strip(_EDGE_PUNCTUATION) for field in fields):
        if any(char.isalnum() for char in field) and (not kept or kept[-1].casefold() != field.casefold()):
            kept.append(field)
    return ", ".join(kept)


def _numbered_affiliations(authors: Tag) -> list[str]:
    """Affiliations written as numbered lines after the author names.

    Superscript markers are kept here: they are what identifies these lines.
    """
    return [match.group("name") for match in _NUMBERED_LINE_RE.finditer(_numbered_text(authors))]


def _numbered_text(block: Tag) -> str:
    """The text of an author block, a line starting at each marker glued to the next word.

    Free-form blocks write several numbered affiliations on one line: "University of
    California, Berkeley ²Duke University ³Carnegie Mellon University" (2609.38079). A
    marker glued to the word after it introduces an affiliation; one after a name is
    followed by a space.
    """
    copy = BeautifulSoup(str(block), "html.parser")
    for sup in copy.select("sup"):
        after = sup.next_sibling
        text = after.get_text() if isinstance(after, Tag) else str(after or "")
        if text[:1].isalpha() and not _inside_word(sup):
            sup.insert_before("\n")
    return copy.get_text().replace("\xa0", " ")


def _dedupe(candidates: list[str]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    for candidate in candidates:
        for affiliation in clean_affiliations(candidate):
            seen.setdefault(affiliation.casefold(), affiliation)
    return tuple(seen.values())


def clean_affiliations(text: str) -> tuple[str, ...]:
    """The affiliations in one candidate string, each normalized by :func:`clean_affiliation`.

    Usually one; none when the string is not an affiliation; several for IEEE's "X, China,
    and also with Y", which gives its people both.

    Args:
        text: A candidate string, from a page or from stored data.

    Returns:
        The affiliations, in order (possibly empty).
    """
    # A role ("X is Robotics Lead at Y") is no statement of thanks notes: the string is one.
    statements = (_stated_affiliations([text]) or [text]) if _people(text) else [text]
    return tuple(
        affiliation
        for statement in statements
        for part in _ALSO_WITH_RE.split(statement)
        for piece in marked_pieces(" ".join(part.split()))
        if (affiliation := clean_affiliation(piece))
    )


def marked_pieces(text: str) -> list[str]:
    """The affiliations of a string that numbered markers written as text run together.

    "Cornell University 2University of California, Berkeley" is two (AFF-23). A marker is
    one or two digits glued to a capitalized word ("2Duke", "3HKUST", "4eBay") after a
    space; the word before holds no digit, unless it is itself marked ("2CASIA 3HKUST"), so
    that postcodes stay whole ("London WC1E 6AE", "QC H2S 3H1"), and so do "3D Vision Lab"
    or "4K" (one letter).

    Args:
        text: A candidate string, from a page or from stored data.

    Returns:
        The pieces, each with its marker, which cleaning strips; the text alone when it
        holds no marker.
    """
    cuts = []
    for match in _INLINE_MARKER_RE.finditer(text):
        word = text[match.end() : match.end() + 2]
        before = text[: match.start()].split()
        if (word[0].isupper() or word[1].isupper()) and (
            not any(char.isdigit() for char in before[-1]) or _MARKED_WORD_RE.fullmatch(before[-1])
        ):
            cuts.append(match.start())
    return [text[start:end] for start, end in zip([0, *cuts], [*cuts, len(text)], strict=True)]


def clean_affiliation(text: str) -> str | None:
    """Normalize one affiliation string, or return ``None`` if it is not an affiliation.

    Contact details are removed, including obfuscated addresses and lists of mailbox names,
    and so are the people an IEEE sentence starts with: "A and B are with X" gives X. A
    string holding several affiliations is split first, by :func:`clean_affiliations`.
    """
    text = _CONTACT_TAIL_RE.sub("", _MACRO_RE.sub("", text.replace("\xa0", " ")))
    text = _MAILBOX_LIST_RE.sub(" ", _OBFUSCATED_EMAIL_RE.sub(" ", text))
    text = _EMPTY_BRACKETS_RE.sub(" ", _LINK_LABEL_RE.sub(" ", _LATEX_SPACE_RE.sub(" ", text)))
    if _NOISE_RE.search(text):
        return None
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", " ".join(_unglued(text).split()))
    text = _REPEATED_COMMA_RE.sub(",", text)
    text = _LEADING_MARKER_RE.sub("", text)
    # After the marker strip, which would eat a leading postcode value.
    if _KEYVAL_RE.search(text):
        text = _keyval_text(text)
    if people := _people(text):
        text = text[people.end() :]
    # A list cut after its connector ("The University of Hong Kong, and", 2609.04958) or a
    # dash ("Hamburg, Germany -"): what precedes it stands alone.
    text = _LIST_END_RE.sub("", text.strip(_EDGE_PUNCTUATION)).rstrip(_EDGE_PUNCTUATION + "-\u2013")
    text = _CONNECTOR_RE.sub("", text)
    if len(text) < _MIN_LENGTH or not any(char.isalpha() for char in text) or _JUNK_RE.fullmatch(text):
        return None
    # A contact detail the rules above did not strip: the whole string goes, rather than a
    # store `validate` refuses, which a data workflow does not push (AFF-32).
    if has_contact(text):
        return None
    return text


def has_contact(text: str) -> bool:
    """Whether the text holds a contact detail, which the data contract keeps out of affiliations.

    The cleaning drops a string that still holds one, and ``validate`` refuses a store that
    does: both ask this.
    """
    return _CONTACT_RE.search(text) is not None


def _unglued(text: str) -> str:
    """The text with a comma where LaTeXML glued two parts of an affiliation (see ``_GLUE_RE``).

    "Department of Computer Science and EngineeringMichigan State University" becomes
    "Department of Computer Science and Engineering, Michigan State University".
    """
    pieces: list[str] = []
    start = 0
    for match in _GLUE_RE.finditer(text):
        at = match.start()
        part = text[text.rfind(",", 0, at) + 1 : at]
        word = part.rsplit(maxsplit=1)[-1] if part.split() else ""
        inside_brackets = part.count("(") > part.count(")")
        if text[at - 1] == ")" or (_UNIT_WORD_RE.search(part) and "-" not in word and not inside_brackets):
            pieces.append(text[start:at] + ", ")
            start = at
    return "".join(pieces) + text[start:]


def states_people(text: str) -> bool:
    """Whether the text is a sentence about people: "A and B are with X", "The authors are with X".

    Args:
        text: An affiliation candidate or a stored affiliation string.

    Returns:
        ``True`` when its affiliation follows the people it names.
    """
    return _people(text) is not None


def _people(text: str) -> re.Match[str] | None:
    """The people an "A and B are with X" sentence starts with, verb included.

    ``None`` when the text does not start that way, or when what precedes the verb names an
    institution, as it is then not a list of people.
    """
    match = _SUBJECT_RE.match(text)
    if match is None or _INSTITUTION_WORD_RE.search(match.group("subject")):
        return None
    return match


def names_only_authors(text: str, authors: Sequence[str]) -> bool:
    """Whether an affiliation candidate only names some of the paper's own authors.

    LaTeX classes put names where affiliations go: "Nicolás Ugrinovic", "Yiqun Zhang, and
    Yiu-Ming Cheung", "Benoît Macq Fellow, IEEE, and Christophe De Vleeschouwer Member,
    IEEE". Each name of the list is compared by :func:`name_key`, IEEE grades and "Jr."
    left out. A string with an institution word stays, and so does a collective that signs
    as an author ("Alzheimer's Disease Neuroimaging Initiative").

    Args:
        text: A cleaned affiliation.
        authors: The paper's author names.

    Returns:
        ``True`` when every name of ``text`` is one of ``authors``.
    """
    if _INSTITUTION_WORD_RE.search(text) or _COLLECTIVE_RE.search(text):
        return False
    known = {name_key(_NAME_SUFFIX_RE.sub(" ", author)) for author in authors}
    names = [
        key for name in _SEVERAL_PEOPLE_RE.split(_NAME_SUFFIX_RE.sub(" ", text)) if (key := name_key(name))
    ]
    return bool(names) and all(key in known for key in names)


def _author_affiliations(
    html: str, authors: tuple[str, ...], affiliations: tuple[str, ...], *, partial: bool
) -> AuthorAffiliations | None:
    """Map each author to their affiliations, as indices into ``affiliations``.

    Tried in order: a single affiliation or author (trivial), one affiliation block per
    author, superscript markers matched with marked lines and notes, and "A and B are
    with X" sentences. ``None`` when the page never says who is where; a ``None`` entry
    when it says it only for the other authors. A single affiliation is not everyone's
    when its source left lines out (``partial``): author names dropped next to it, as the
    page had placed people elsewhere, or lines of a block without markers that may be
    other affiliations ("Tencent HY" beside "Southeast University", 2610.14852).
    """
    if not authors or not affiliations:
        return None
    if len(authors) == 1 or (len(affiliations) == 1 and not partial):
        return (tuple(range(len(affiliations))),) * len(authors)
    # The soup of the paper-level pass was pruned in place: parse a fresh one.
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("div.ltx_authors") is None:
        return None
    index_of = {affiliation.casefold(): index for index, affiliation in enumerate(affiliations)}
    for tier in (_per_creator_map, _marker_map, _thanks_map):
        if (mapping := tier(soup, authors, index_of)) is not None:
            return mapping
    return None


def _per_creator_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """One affiliation block per author (ACM- and IEEE-like classes)."""
    creators = _creators(soup, authors, index_of)
    if not any(indices for _, indices, _ in creators):
        return None
    if len(creators) > 1 and not any(indices for _, indices, _ in creators[:-1]):
        # Only the last author carries affiliations: LaTeXML attaches a block shared by
        # every author to the last one, which says nothing about who is where.
        return None
    places = {index for affiliation, index in index_of.items() if is_place(affiliation)}
    people: list[tuple[str, tuple[int, ...]]] = []
    for name, indices, marked in creators:
        if not _several_people(name, authors):
            people.append((name, indices))
        elif (
            len(creators) > 1
            and not marked
            and "," not in name
            and _PAIR_RE.search(name)
            and not set(indices) <= places
        ):
            # A pair beside other creators, their block under both names and no marker to
            # tell them apart: "Zhiyuan Yang & Jiahao Cheng" share it (2609.36407). Not a
            # block that only names a place, the end of an address the creators before
            # began ("Orlando, FL 32816, USA", 2609.34021): the pair would be placed nowhere.
            people += [(person, indices) for person in _PAIR_RE.split(name)]
        # Otherwise a creator naming several people ("A, B and C", or all of them in one
        # creator) says nothing about which of them is where: markers may.
    aligned = _align([name for name, _ in people], authors)
    if aligned is None:
        return None
    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    for creator_index, author_index in aligned.items():
        mapping[author_index] = people[creator_index][1] or None
    return tuple(mapping) if any(mapping) else None


def _creators(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> list[tuple[str, tuple[int, ...], bool]]:
    """The people of the author block: each one's name, affiliations, and whether markers follow it.

    An affiliation glued to a name is that person's (2610.17412).
    """
    creators: list[tuple[str, tuple[int, ...], bool]] = []
    for creator in soup.select("div.ltx_authors span.ltx_creator.ltx_role_author"):
        name = creator.select_one(".ltx_personname")
        if name is None or not _names_a_person(name, authors):
            continue
        contacts = _contact_segments(
            (_pruned(contact) for contact in creator.select(".ltx_role_affiliation, .ltx_role_address")),
            authors,
        )
        person = _plain_text(name)
        if (glued := _glued_name(person, authors)) is not None:
            person, affiliation = glued
            contacts.append(affiliation)
        marked = _pruned(name).select_one("sup") is not None
        creators.append((person, _indices(contacts, index_of), marked))
    return creators


def _names_a_person(name: Tag, authors: Sequence[str]) -> bool:
    """Whether a creator's name is a person's.

    Not a link set as an author ("Project Page", a repository: 2609.37107), nor what else
    LaTeXML makes creators of (2610.12978): an address ("author@taobao.com"), or a line
    led by a marker ("²Alibaba Group", "✉Corresponding author") that names no author. Left
    in, the last of them would hide that only the last person carries the shared block.
    """
    text = _plain_text(_pruned(name))
    if not text or all("@" in word for word in text.replace(",", " ").split()):
        return False
    return _leading_marker(name) is None or names_only_authors(text, authors)


def _several_people(name: str, authors: Sequence[str]) -> bool:
    """Whether a creator names several people: separators, or several authors' names.

    2610.01434 writes its eight authors in one creator separated by wide spaces only.
    """
    folded = _fold(name)
    return (
        _SEVERAL_PEOPLE_RE.search(name) is not None or sum(_fold(author) in folded for author in authors) > 1
    )


def _marker_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """Superscript markers on names, matched with marker-led affiliation lines and notes."""
    block = soup.select_one("div.ltx_authors")
    if block is None:  # pragma: no cover - _author_affiliations only maps pages with an author block
        return None
    names = _fold(" , ".join(_marked_text(name) for name in block.select(".ltx_personname")))
    anchors = _anchors(soup, block, index_of)
    if not anchors:
        return None

    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    resolved = 0
    for position, author in enumerate(authors):
        match = re.search(re.escape(_fold(author)) + r"[,\s]*" + _MARKER_RUN_RE, names)
        if match is None:
            continue
        markers = [
            marker
            for token in _MARKED_RE.findall(match.group(1))
            for marker in _MARKER_SPLIT_RE.split(token)
            if marker
        ]
        indices: list[int] = []
        for marker in _expand(markers, anchors):
            if marker in anchors:
                indices.extend(index for index in anchors[marker] if index not in indices)
            elif not set(marker) <= _SYMBOL_MARKERS:
                # An affiliation-like marker without an anchor: the anchor set is wrong.
                return None
        if indices:
            mapping[position] = tuple(indices)
            resolved += 1
    return tuple(mapping) if resolved else None


def _expand(markers: Iterable[str], anchors: Mapping[str, tuple[int, ...]]) -> list[str]:
    """Split marker runs written without separators ("⋆†", "12", "6*‡") into known markers.

    Symbols come off a number first: "2,6*‡" places its author at 2 and 6 (2609.38079).
    """
    expanded: list[str] = []
    for run in markers:
        parts = [run] if run in anchors else [part for part in _SYMBOL_SPLIT_RE.split(run) if part]
        for marker in parts:
            if marker not in anchors and len(marker) > 1 and all(char in anchors for char in marker):
                expanded.extend(marker)
            else:
                expanded.append(marker)
    return expanded


def _anchors(soup: BeautifulSoup, block: Tag, index_of: Mapping[str, int]) -> dict[str, tuple[int, ...]]:
    """Affiliations introduced by a marker, as ``marker -> affiliation indices``."""
    article = soup.select_one("article.ltx_document") or soup
    nodes: list[Tag] = list(block.select(".ltx_role_affiliation, .ltx_role_address"))
    nodes += soup.select(_AFFILIATION_NOTES)
    nodes += article.find_all("span", class_="ltx_role_footnotetext", recursive=False)
    # Thanks notes that number their affiliation ("¹FZI Research Center...", 2609.03677), by
    # their markers only: their own mark, the same for every note, names no affiliation.
    thanks = [
        note
        for note in soup.select(".ltx_note.ltx_role_thanks")
        if not _OTHER_THANKS & set(note.get_attribute_list("class"))
    ]

    anchors: dict[str, tuple[int, ...]] = {}

    def add(marker: str, candidate: str) -> None:
        if indices := _anchored(candidate, index_of):
            anchors.setdefault(marker.strip(), indices)

    for node in [*nodes, *thanks]:
        label = node.select_one(".ltx_note_mark") if node not in thanks else None
        marked = _marked_text(_pruned(node))
        # Markers may lead ("¹ETH Zurich") or trail ("Tampere University¹") their
        # affiliation: keep the orientation that explains more of the node.
        leading = [
            (marker, candidate)
            for run, candidate in _ANCHOR_RE.findall(marked)
            if _known(candidate, index_of)
            for marker in _MARKED_RE.findall(run)
        ]
        trailing = [
            (marker, candidate)
            for candidate, marker in _TRAILING_ANCHOR_RE.findall(marked)
            if _known(candidate, index_of)
        ]
        pairs = max(leading, trailing, key=len)
        if pairs:
            for marker, candidate in pairs:
                add(marker, candidate)
        elif label is not None:
            # A note whose only marker is its own mark: "1institutetext: ...".
            add(_plain_text(label), _MARKED_RE.sub(" ", marked))
    # Free-form blocks write the marker as plain text: "1ETH Zurich", or a symbol: "*Oregon
    # State University" (2610.17605), which anchors only an affiliation, not "*Equal contribution".
    text = _numbered_text(_pruned(block))
    for match in (*_NUMBERED_ANCHOR_RE.finditer(text), *_SYMBOL_LINE_RE.finditer(text)):
        add(match.group("marker"), match.group("name"))
    return anchors


def _known(candidate: str, index_of: Mapping[str, int]) -> bool:
    """Whether the candidate cleans to one of the paper's affiliations, or is made of them."""
    return bool(_anchored(candidate, index_of))


def _anchored(candidate: str, index_of: Mapping[str, int]) -> tuple[int, ...]:
    """The affiliations of the text after a marker: the one it cleans to, or those it is made of.

    A marker's text runs to the next marker, read as one line: it may hold the lines an
    affiliation was joined from, then another affiliation of the same marker:
    "⟨2⟩Laboratory for intelligent Global Health and Humanitarian Response / Technologies
    (LiGHT) / Swiss Federal Institute of Technology (EPFL), Lausanne, Switzerland"
    (2610.03290). It is then cut into the paper's affiliations, one after another, without
    regard to commas; a text that is not wholly made of them anchors nothing.
    """
    if indices := _indices([candidate], index_of):
        return indices
    loose = {_loose(affiliation): index for affiliation, index in index_of.items()}
    rest = _loose(candidate.strip(_EDGE_PUNCTUATION))
    found: list[int] = []
    while rest:
        head = max((key for key in loose if rest == key or rest.startswith(f"{key} ")), key=len, default=None)
        if head is None:
            return ()
        found.append(loose[head])
        rest = rest[len(head) :].strip()
    return tuple(dict.fromkeys(found))


def _thanks_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """Sentences naming who is where: "A. Author and B. Author are with the X".

    They are written in thanks notes, and by some classes in the affiliation macro.
    """
    notes = soup.select(".ltx_note.ltx_role_thanks")
    notes += soup.select("div.ltx_authors .ltx_role_affiliation, div.ltx_authors .ltx_role_address")
    return _sentence_map([_note_text(_pruned(note)) for note in notes], authors, index_of)


def map_stated_affiliations(
    texts: Iterable[str], authors: Sequence[str], affiliations: Sequence[str], *, everyone: bool = True
) -> AuthorAffiliations | None:
    """Place the authors that "A and B are with X" sentences name, as the page parser does.

    Args:
        texts: Text holding the sentences, such as stored affiliation strings.
        authors: The paper's author names, in order.
        affiliations: The paper's affiliations, which the sentences' affiliations must clean to.
        everyone: Whether "The authors are with X" places every author. A footnote shared by
            some of them says it too.

    Returns:
        For each author, the indices of their affiliations (``None`` for an author no
        sentence names), or ``None`` when no sentence places anybody.
    """
    index_of = {affiliation.casefold(): index for index, affiliation in enumerate(affiliations)}
    return _sentence_map(texts, tuple(authors), index_of, everyone=everyone)


def _sentence_map(
    texts: Iterable[str], authors: tuple[str, ...], index_of: Mapping[str, int], *, everyone: bool = True
) -> AuthorAffiliations | None:
    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    resolved = 0
    sentences = [
        sentence
        for text in texts
        for line in text.splitlines()
        for sentence in _SENTENCE_SPLIT_RE.split(line)
    ]
    for sentence in sentences:
        match = _IS_WITH_RE.search(sentence)
        if match is None:
            continue
        value = _NEXT_SENTENCE_RE.split(_CONTACT_TAIL_RE.sub("", sentence[match.end() :]), maxsplit=1)[0]
        indices = _indices([value], index_of)
        if not indices:
            continue
        subject = _fold(sentence[: match.start()])
        if _ALL_AUTHORS_RE.search(subject):
            placed: Iterable[int] = range(len(authors)) if everyone else ()
        else:
            placed = [
                position for position, author in enumerate(authors) if _named_in(subject, author, authors)
            ]
        for position in placed:
            entry = mapping[position] or ()
            if new := tuple(index for index in indices if index not in entry):
                mapping[position] = (*entry, *new)
                resolved += 1
    return tuple(mapping) if resolved else None


def _named_in(subject: str, author: str, authors: tuple[str, ...]) -> bool:
    """Whether the folded ``subject`` names the author, possibly with initials.

    "E. Milara" names Eva Milara when no other author shares that initial and surname.
    """
    folded = _fold(author)
    if folded in subject:
        return True
    first, _, surname = folded.partition(" ")
    if not surname:
        return False
    initial = first[:1]
    surname = surname.rsplit(maxsplit=1)[-1]
    twins = sum(
        1
        for other in authors
        if (other_parts := _fold(other).split())
        and other_parts[0][:1] == initial
        and other_parts[-1] == surname
    )
    if twins != 1:
        return False
    pattern = rf"\b{re.escape(initial)}[\w'-]*\.?(?:\s+[\w'.-]+)*?\s+{re.escape(surname)}\b"
    return re.search(pattern, subject) is not None


def _align(names: Sequence[str], authors: tuple[str, ...]) -> dict[int, int] | None:
    """Match creator names to the listing's authors.

    Folded full names first, then surname plus first initial, then position when both
    lists have the same length. An ambiguous name fails the whole alignment: a wrong
    author-affiliation pair is worse than none.
    """
    folded = [_fold(author) for author in authors]
    result: dict[int, int] = {}
    used: set[int] = set()
    unmatched: list[int] = []
    for position, name in enumerate(names):
        target = _fold(name)
        hits = [j for j, author in enumerate(folded) if author == target and j not in used]
        if not hits and (parts := target.split()):
            hits = [
                j
                for j, author in enumerate(folded)
                if j not in used and author.rsplit(maxsplit=1)[-1] == parts[-1] and author[:1] == parts[0][:1]
            ]
        if len(hits) > 1:
            return None
        if hits:
            result[position] = hits[0]
            used.add(hits[0])
        else:
            unmatched.append(position)
    if len(names) == len(authors):
        for position in unmatched:
            if position not in used:
                result[position] = position
                used.add(position)
    return result or None


def _indices(candidates: Iterable[str], index_of: Mapping[str, int]) -> tuple[int, ...]:
    """Indices of the candidates that clean to a known affiliation, deduplicated.

    Commas do not count: a marked line read as one text ("Department of Computer Science
    University of Central Florida") is the affiliation its lines were joined into
    ("Department of Computer Science, University of Central Florida", 2610.02000).
    """
    loose = {_loose(affiliation): index for affiliation, index in index_of.items()}
    found: list[int] = []
    for candidate in candidates:
        for affiliation in clean_affiliations(candidate):
            index = index_of.get(affiliation.casefold(), loose.get(_loose(affiliation)))
            if index is not None and index not in found:
                found.append(index)
    return tuple(found)


def _loose(affiliation: str) -> str:
    return " ".join(affiliation.casefold().replace(",", " ").split())


def _pruned(node: Tag) -> Tag:
    """A copy of the node without contact labels, e-mails, links and note decorations.

    The copied node itself is kept even when it is a note: only what it contains is noise.
    """
    copy = BeautifulSoup(str(node), "html.parser")
    root = next(iter(copy.find_all(name=True, limit=1)), None)
    for noise in copy.select(
        ".ltx_contact_name, .ltx_role_email, .ltx_note, .ltx_note_mark, .ltx_note_type, a"
    ):
        if noise is not root:
            noise.decompose()
    return copy


def _marked_text(node: Tag) -> str:
    """Node text with each superscript rendered as a ``⟨marker⟩`` token."""
    copy = BeautifulSoup(str(node), "html.parser")
    for sup in copy.select("sup"):
        sup.replace_with(sup.get_text() if _inside_word(sup) else f"⟨{' '.join(sup.get_text().split())}⟩")
    return " ".join(copy.get_text().split())


def _inside_word(sup: Tag) -> bool:
    """Whether a superscript is part of a word ("Hyper<sup>2</sup>labs") rather than a marker.

    Between two lowercase letters only: a marker between words ("University<sup>1</sup>Nokia")
    still separates them.
    """
    before, after = sup.previous_sibling, sup.next_sibling
    return (
        isinstance(before, NavigableString)
        and before[-1:].islower()
        and isinstance(after, NavigableString)
        and after[:1].islower()
    )


def _plain_text(node: Tag) -> str:
    """Node text without superscripts, whitespace collapsed."""
    copy = BeautifulSoup(str(node), "html.parser")
    for sup in copy.select("sup"):
        sup.decompose()
    return " ".join(copy.get_text().split())


# Curly quotes and long dashes fold to their ASCII forms: "Shin\u2019ichi" == "Shin'ichi".
_PUNCTUATION_VARIANTS = str.maketrans("\u2018\u2019\u02bc\u2013\u2014\u2212", "'" * 3 + "-" * 3)


def _fold(text: str) -> str:
    """Lowercase, strip accents and normalize punctuation, for name comparison."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_PUNCTUATION_VARIANTS))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


# Apostrophes and LaTeX accent leftovers join the letters around them ("Niccol`o" is "Niccolò").
_NAME_JOINERS_RE = re.compile(r"['`^~\"]")


def name_key(name: str) -> tuple[str, ...]:
    """Key under which two spellings of one person's name compare equal.

    Case, accents, punctuation and word order are ignored, so a new version of a paper
    that respells an author ("Ma Ziqi" as "Ziqi Ma", "Niccol`o" as "Niccolò") keeps them.

    Args:
        name: An author name as listed.

    Returns:
        The name's words, folded and sorted.
    """
    return tuple(sorted(re.findall(r"[^\W_]+", _NAME_JOINERS_RE.sub("", _fold(name)))))
