"""The words and patterns of the affiliation extraction, shared by every step of it.

Each rule came from a real page, whose arXiv id its comment names (``docs/extraction.md``):
never simplify one away. ``make knockout`` finds those no test asserts on (EXT-2).
"""

import re
import unicodedata

# LaTeXML renders line breaks and \quad between affiliations as newlines, em spaces
# or runs of (non-breaking) spaces.
_SEPARATOR_RE = re.compile(r"\n|\u2003|\s{2,}")
# The example authors of ICLR's and NeurIPS's templates, left in by some: "Department of
# Computer Science, Cranberry-Lemon University" (2610.27759, 2502.10841), "University of the
# Witwatersrand, Joburg" (2610.27759), not the real one's "Johannesburg" (2405.01828). Noise,
# and the rest of their contacts goes with them ("Pittsburgh, PA 15213", 2502.10841).
_TEMPLATE_EXAMPLE_RE = re.compile(r"cranberry-lemon|witwatersrand,?\s+joburg", re.IGNORECASE)
# Contact details and footnotes that are not affiliations.
_NOISE_RE = re.compile(
    r"@|https?://|www\.|equal(ly)?(?: senior)? contribut|contributed equally|correspond|work done"
    r"|project lead|senior author|first author|co-first|joint first|equal advising|internship"
    # Phone numbers and an author's placeholder: "Tel.: +49 ...", "TODO: X's affiliation".
    r"|\btel\.?\s*:|\bfax\s*:|\btodo\b"
    # CVPR's placeholders: "Institution2", "First line of institution2 address" (2309.04907).
    r"|\binstitution\s*\d"
    rf"|{_TEMPLATE_EXAMPLE_RE.pattern}",
    re.IGNORECASE,
)
# Where an author went since, or interned: "now at Microsoft Research" (2202.07643), "Interns
# at Shanghai AI Laboratory" (2505.23656), "Done as intern at Zhipu AI" (2311.03079). Notes,
# which the cleaning drops; the tiers still read a line of them as a sentence ("†Now at
# Google" tells symbols that mark notes).
_LATER_NOTE_RE = re.compile(
    r"\bnow\s+(?:at|with)\b|\binterns?\s+at\b|\bas\s+(?:an?\s+)?intern\b", re.IGNORECASE
)
# ORCID identifiers, with their label: "(ORCID: 0000-0002-1117-9355)" after an affiliation
# (2305.17033), the list after one ("ORCID codes: FT 0009-…; PB 0000-…", 2610.13604), never
# past a bracket, or the label alone (2610.26079).
_ORCID_ID = r"(?:\d{4}-){3}\d{3}[\dX]?\b"
_ORCID_RE = re.compile(
    rf"[(\[]?\s*\borcid\b[^\d()\[\]]*{_ORCID_ID}[)\]]?(?:[^()\[\]]*?{_ORCID_ID})*|\borcid\b\s*:?\s*$",
    re.IGNORECASE,
)
# A contribution note LaTeXML glued to the affiliation after it, which the note's noise
# would drop whole: "Equal senior contributionsDeepMind" (ar5iv's 2204.14198).
_GLUED_NOTE_RE = re.compile(
    r"^\W*equal(?:ly)?\s+(?:senior\s+)?contribut(?:ions?|ors?)(?-i:(?=[A-Z]))", re.IGNORECASE
)
# The vertical space of a LaTeX line break (\\[5pt]), which LaTeXML prints as text.
_LATEX_SPACE_RE = re.compile(r"\[\s*-?\d*\.?\d+\s*(?:pt|em|ex|mm|cm|in|bp|pc|mu)\s*\]")
# The label of a link whose address is removed as a contact detail, sometimes glued to the
# affiliation before it: "MITProject page"; "Project:" with its colon only, glued to the last
# author's name ("Li YuanProject: https://…", 2406.18522).
_LINK_LABEL_RE = re.compile(
    r"project(?:\s+(?:page|website|homepage|repository|site)\b\s*:?|\s*:)", re.IGNORECASE
)
# Contact details after an affiliation: "..., USA. email: {a, b}@nyu.edu", "(e-mail: ...)",
# an address in brackets, which unwrapped thanks notes glue to the sentence: "..., Hong
# Kong SAR, China (author@connect.ust.hk)" (2609.10082), or one that ends the line: "...,
# Vienna, Austria author@technikum-wien.at" (2610.02974), mailboxes included: "...,
# Germany. {jane.doe, jroe}@tum.de" (2610.03283), the sentence's full stop after it: "...,
# Italy. {name.surname}@unitn.it." (2609.28184). Its label may be glued to the country
# before it: "..., MI, USAEmail:" (2608.29996). A list in braces ends it even glued to the
# country: "..., Singapore{jane,john}@nus.edu.sg" (ar5iv's 1312.4400). Several addresses
# go together, which a comma after the first joined across lines: "University of California
# Santa Cruz{…}@stu.pku.edu.cn," / "author@u.nus.edu, author@ucsc.edu" (2406.18522).
_CONTACT_TAIL_RE = re.compile(
    r"\(?\s*\be-?mails?\b.*$|(?<=[a-z])e-?mails?\s*:.*$|[(\[]\s*[\w.+-]+@.*$"
    r"|(?:\s|(?=\{))(?:(?:\{[^{}]*\}|[\w.+-]+)@[\w-]+(?:\.[\w-]+)+[.,;]?\s*)+$",
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
# A mailbox or a mail domain printed without its "@" (EXT-3): "gmail.com", "mails.tsinghua.
# edu.cn", "sarthaktripathi3.gmail.com", or a lone mailbox name, "wangbohua.wbh"; not a lab
# named after its domain ("valeo.ai", "realiz.ai").
_MAIL_FRAGMENT_RE = re.compile(
    r"\b(?:gmail|googlemail|outlook|hotmail|yahoo|qq|163|126|foxmail|icloud)\.com\b"
    r"|\bmails?\.[\w-]+(?:\.[\w-]+)*\.(?:edu|ac)(?:\.[a-z]{2})?\b"
    r"|^[a-z0-9]+(?:[._][a-z0-9]+)*\.(?!(?:ai|io|com|net|org|edu|gr|de|cn|uk|fr|jp|kr|co|app|dev|tech)$)[a-z]{1,4}$"
)
# What is left of a contact detail in brackets: "University of Zurich, Switzerland ()".
_EMPTY_BRACKETS_RE = re.compile(r"\(\s*\)|\[\s*\]")
# Mailbox names whose "@domain" is printed elsewhere: "{jane.doe, john.roe}", sometimes
# unclosed, the list going on in another node, whose affiliation the line join glues on:
# "{jane.doe,jroe,john_roe,jdoe, Apple" (2410.23054). A name is in lower
# case, or capitalized when dots or underscores join its parts ("{Jane.Doe, A.Roe",
# 2610.25235), which the words of an affiliation, after which an unclosed list ends, never are.
# A dotted lowercase name fits both forms: each name is matched whole and once (an atomic
# group), else a list that ends on nothing the pattern takes ("jdoe)", "o'brien") tried every
# way of reading each name, twice as long at each one more (EXT-1).
_MAILBOX = r"(?>(?:[A-Za-z0-9+-]+(?:[._][A-Za-z0-9+-]+)+|[a-z0-9_.+-]+)(?![A-Za-z0-9_.+-]))"
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
# The same people's next affiliation in one sentence: "is with X and is also with Y". The
# cleaning drops such a connector too (`_LIST_END_RE`, `_CUT_CONNECTOR_RE`), which no test
# can tell from this rule (EXT-2): it keeps the sentence's text clean for `_names_a_place`.
_TRAILING_CONNECTOR_RE = re.compile(r"[\s,]+(?:and|&)\s*$", re.IGNORECASE)
# Sentences that follow an affiliation in acknowledgment notes.
_NEXT_SENTENCE_STARTS = (
    r"(?:This|These|The\s+work|Corresponding|Manuscript|He|She|They|We|Our|Work|Part|Funding|Supported)\b"
)
_NEXT_SENTENCE_RE = re.compile(rf"\.\s+(?={_NEXT_SENTENCE_STARTS})")
# The symbols superscripts mark with: those of contribution notes rather than affiliations
# (U+2217 is LaTeX's \ast), and those some classes mark affiliations with ("★ Ropedia",
# 2610.29997). Every marker pattern below is built from them (EXT-7).
_NOTE_SYMBOLS = "*\u2217†‡§¶⋆♯♭#°ª"
_MARKER_SYMBOLS = re.escape("".join(sorted(_NOTE_SYMBOLS + "♠♣♢♡★")))
# A line of a note that starts a sentence of its own, or a footnote marker: "* Equal Contribution".
_SENTENCE_START_RE = re.compile(
    rf"\s*(?:{_NEXT_SENTENCE_STARTS}|[{re.escape(_NOTE_SYMBOLS)}]|\(?e-?mails?\b)", re.IGNORECASE
)
# Leading footnote markers: "1 Cornell University", "* MIT", "†‡ NVIDIA", the asterisk
# operator before "University of Oxford" (2609.35052). Digits that start a name are not
# markers: "54th Research Institute", "3M Company", "3D Vision Lab".
_LEADING_MARKER_RE = re.compile(rf"^(?:[\s,{_MARKER_SYMBOLS}]|\d+(?!\d|(?:st|nd|rd|th|[DKM])\b))+")
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
# An address in a span of text right after the word before it: "University of
# Oxford<tt>author@robots.ox.ac.uk</tt>" reads "Oxfordauthor@robots.ox.ac.uk", which the
# contact cleanup takes away whole, leaving "University of" (ar5iv's 2006.13662); in
# italics too, "University of Washington<i>author@unc.edu</i>" (2412.06141). A space
# sets it apart; an "@" set in its own span, or after a brace, stays where it is
# ("linyida<tt>@</tt>myvuw.ac.nz", 2609.13233).
_GLUED_ADDRESS_RE = re.compile(
    r'(?<=[^\W_])(?=<span\b[^>]*\bclass="[^"]*\bltx_(?:text|font_typewriter)\b[^>]*>[\w{][^<@]*@)'
)
# A superscript set by hand, as a span raised by its style, holding a marker only: "Yunze
# Liu<span style="font-size:70%;position:relative; bottom:2.4pt;">1,*</span>" and "1 NVIDIA
# 2 MIT 3 UCB" of 2610.19495, read as one affiliation without them.
_RAISED_RE = re.compile(r"position:\s*relative;\s*bottom:\s*\d", re.IGNORECASE)
_RAISED_MARKER_RE = re.compile(rf"[\d,\s{_MARKER_SYMBOLS}]{{1,12}}")
# Conjunctions left over when a line break splits "A University and B Institute".
_CONNECTOR_RE = re.compile(r"^(?:and|&)(?:\s+|$)", re.IGNORECASE)
# A line that ends like this continues on the next one ("School of Medicine, and").
_CONTINUED_RE = re.compile(r"(?:,|\band|&)\s*$", re.IGNORECASE)
# So does one that ends with a preposition: "Key Laboratory ... of Ministry of" / "Education"
# (2609.11477). Lowercase only: "TU Wien, AT" ends with a country code.
# After a space: "technikum-wien.at" ends an address (2610.02974).
_DANGLING_RE = re.compile(r"(?<=\s)(?:of|for|the|at|in|on|de|du|des|der|für|und)\s*$")
# The connector of a list cut after it: "The University of Hong Kong, and".
_LIST_END_RE = re.compile(r"\s*,\s*(?:and|&)$", re.IGNORECASE)
# One without a comma, where LaTeX's \and ended an affiliation and LaTeXML lost what
# followed: "The University of Texas at Austin and" (2410.14919), "ECE &" (2610.16337).
# What precedes it stands alone, unless it is a name cut short, which a word like these
# ends: "Hong Kong University of Science and", "Nanjing University of Posts and".
_CUT_CONNECTOR_RE = re.compile(r"\s+(?:and|&)$")
_NAME_GOES_ON_RE = re.compile(
    r"\b(?:Sciences?|Technolog(?:y|ies)|Engineering|Posts|Telecommunications?|Arts|Mathematics"
    r"|Design|Information|Medicine|Health|Physics|Economics|Management|Education)$"
)
# A LaTeX command LaTeXML printed as text, glued to what follows: "\addrDepartment of ...".
# Its name is lowercase there: the capital starts the affiliation, or the number of the
# affiliation's marker, which then goes as a leading marker: "\affilnum1Department of ..."
# (SAGE's template, 2610.18363, 2509.06285), "\authormark2Department of ..." (2505.14715).
_MACRO_RE = re.compile(r"\\(?:[a-z]+(?=[A-Z\d])|[A-Za-z]+\*?(?:\s+|$))")
# The TeX source of a symbol LaTeXML printed after it, in strings read before the source was
# dropped (`_ANNOTATION_RE`): "Φ\Phi-lab, ESRIN" (2609.06187), a gamma before "\gamma-Robotics"
# (2609.37250).
# Not a backslash a name holds: "Institute of Creative\Media/Technologies" (2608.29287).
_TEX_SOURCE_RE = re.compile(r"(?<=[^\x00-\x7f])\\[A-Za-z]+")
# A note on the affiliations glued to the last one: "German Cancer Research Center (DKFZ),
# Full affiliations are given in Appendix .Code, Models & Data" (2411.03670).
_AFFILIATIONS_NOTE_RE = re.compile(
    r",?\s*\b(?:(?:full|complete|all|other)\s+)?affiliations?\s+(?:are|is)\b.*$", re.IGNORECASE | re.DOTALL
)
# A numbered marker written as text inside a string, glued to the next word: " 2Duke".
_INLINE_MARKER_RE = re.compile(r"(?<=\S\s)\d{1,2}(?=[^\W\d_]{2})")
# A word that starts with such a marker: "2CASIA", "2HKUST(GZ)".
_MARKED_WORD_RE = re.compile(r"\d{1,2}[^\W\d_][^\d\s]*")
# Words of institutions. Not "Foundation Model", a team of Li Auto (2609.21449) and the
# subject of half the papers.
_INSTITUTION_WORD_RE = re.compile(
    r"univ|institut|college|school|lab|cent(?:er|re)|hospital|academy|\binc\b|\bltd\b|gmbh|corp|company"
    r"|research|department|faculty|foundation(?!\s+models?\b)|technolog|polytechn",
    re.IGNORECASE,
)
_INSTITUTION_WORD_START_RE = re.compile(rf"\b(?:{_INSTITUTION_WORD_RE.pattern})", re.IGNORECASE)
# A company named after its AI, which holds no institution word: "Stability AI", after a
# table of names (2311.15127), as "Mistral AI" or "Sakana AI". Never a name's end: "Ai" is
# a given name, the capitals are required.
_AI_COMPANY_RE = re.compile(r"\b[A-Z][\w.-]*\s+AI$")
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
    # The author of IEEE's template, left in by some (2312.17663), and templates' placeholders
    # for the affiliations: "Author Affiliation(s)" (2610.01890), "Affiliation", "Address"
    # (2610.27759).
    r"|ieee\s+publication\s+technology\s+department"
    r"|(?:authors?'?\s+)?affiliations?(?:\s*\(s\)?)?|address(?:es)?"
    rf"|(?:{COUNTRIES})\.?",
    re.IGNORECASE,
)
_MAX_PLACE_LENGTH = 60
# An address without its country, on a line of its own after its affiliation: a postcode
# ("Montréal, QC H3C 3J7", "San Francisco, CA 94103") or a street number ("Mühlenstraße 25,
# 10243 Berlin"), as older pages, which ar5iv renders, lay authors' contacts out (AFF-37). A
# number of its own: "42dot by Hyundai" is a company (2610.11060).
_ADDRESS_LINE_RE = re.compile(r"\b\d+\b|\b[A-Z]\d[A-Z]\b")
# The longest piece of an author field cut at its commas that tells the cut: "College Park".
_MAX_PIECE_WORDS = 2
# A unit whose institution is missing: "Department of Computer Science and Engineering".
_BARE_UNIT_RE = re.compile(
    r"(?:the\s+)?(?:department|dept\.?|school|faculty|division|laboratory|lab|cent(?:er|re)|institute)"
    r"\s+(?:of|for)\b"
    # And in French: "Département d'informatique et de recherche opérationnelle" (1411.1784).
    r"|(?:département|laboratoire|faculté)\s+(?:de|des|du|d['\u2019])",
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
# word or two capitals, or a closing bracket then a word. Only where ``_unglued`` says, so
# that names stay ("AnimSchool", "ByteDance", "McGill"), and never inside brackets
# ("(ShenZhen)").
_GLUE_RE = re.compile(r"(?<=[a-z]{2})(?=[A-Z][a-z]|[A-Z]{2})|(?<=\))(?=[^\W\d_])")
# The first word of an institution's name, glued to a name of several words, as older
# LaTeXML prints an affiliation's lines: "Visual Geometry GroupUniversity of Oxford",
# "Google DeepMindUniversity College London" (ar5iv's 2206.07045, 2512.08924).
_INSTITUTION_START_RE = re.compile(
    r"(?:University|Institute|School|College|Department|Faculty|Laboratory|Academy|Cent(?:er|re)|Hospital)\b"
)
# Words that start such a name rather than end one, a space lost after them: "Shenzhen
# KeyLaboratory of Media Security" (2509.25502), "NationalUniversity of Singapore".
_NAME_START_RE = re.compile(r"Key|National|State|Joint|Normal|Medical|Technical|Graduate|Open")
# A company's suffix, which ends its name: "ByteDance IncShanghai" (ar5iv's 2309.02301).
_COMPANY_SUFFIX_RE = re.compile(r"(?:Inc|Ltd|Corp)\.?")
# A country glued to the name of several words before it, ending its part: "University of
# OxfordUK" (ar5iv's 2206.07045), "NationalUniversity of SingaporeSingapore" (2610.32059).
_GLUED_COUNTRY_RE = re.compile(rf"(?:{COUNTRIES})\.?(?:,|$)")
# Universities LaTeXML ran together, the line breaks between them lost (AFF-41): a name
# ending in "University", then one of a word and "University"; one ending in "University
# of" and a word, then one of a word and "University" without "of" ("The University of
# Adelaide Peking University Huazhong University of Science and Technology", ar5iv's
# 1904.04514), as "University of Southern California University of Washington" is cut
# elsewhere (2311.17946); or a university's country, then a name it starts ("Linköping
# University, Sweden University of Central Florida", 2006.09785).
# Not a country that starts names of its own: "…, China University of Mining and Technology".
_NAME_COUNTRIES = r"China|Hong Kong|Macau|Macao|Taiwan|Korea|Japan|Singapore|India|Qatar"
_RUN_TOGETHER_RE = re.compile(
    r"\bUniversity\s+(?=[A-Z][\w'\u2019-]+\s+University\b)"
    r"|\bUniversity\s+of\s+[A-Z][\w'\u2019-]+\s+(?=[A-Z][\w'\u2019-]+\s+University\b(?!\s+of\b))"
    rf"|\bUniversity,\s+(?!{_NAME_COUNTRIES})(?:{COUNTRIES})\s+(?=(?:University|Institute|College)\b)"
)
# The last word of an institution's name glued to the address after it, as the LaTeX
# source wrote them: "Technion - Israel Institute of Technologyauthor@nvidia.com"
# (ar5iv's 2006.14610), "Zhejiang Universityauthor@gmail.com" (2011.00147). The contact
# cleanup took the word away with the address: a space sets it apart. An address's own
# name is in lower case.
_WORD_BEFORE_ADDRESS_RE = re.compile(
    r"(?<=\S\s)(\S*?(?:University|Universit[aäé]t?|Technology|Institute|College|School"
    r"|Laborator(?:y|ies)|Lab|Research|Sciences?|Engineering|Cent(?:er|re)|Hospital|Academy|Inc|Ltd"
    rf"|{COUNTRIES}))(?=[a-z0-9][\w.+-]+@[\w-]+\.)"
)
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

# Superscripts that mark contribution notes rather than affiliations.
_SYMBOL_MARKERS = frozenset(_NOTE_SYMBOLS)
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
# Markers left beside a name: "Saining Xie 1", "Kai Wang2", "Jane Doe*†".
_NAME_MARKER_RE = re.compile(rf"[\d{_MARKER_SYMBOLS}]+")
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
# Any marker LaTeXML printed as text, its math unparsed, wherever an affiliation holds it:
# "$1$ University of Technology Nuremberg" (2609.24576), "$^a$ ...; $^b$ ..." (three
# affiliations, 2609.32844, with U+02C6 for ^), "$^*$Google Research" (2306.09224), "$2.$
# FAIR Labs" (2210.05663). Each starts an affiliation (EXT-4).
_ANY_TEXT_MARKER_RE = re.compile(r"\$\s*(?:[\^\u02c6]\s*)?\{?\s*[^\s${}]{1,2}?\.?\s*\}?\s*\$")
# Format characters (Unicode's Cf), invisible: zero-width spaces before "Tsinghua University"
# (2303.10137). And LaTeX's ~, printed as a small tilde (U+02DC, after "NVIDIA," in 1511.08861).
_INVISIBLE = dict.fromkeys(
    (code for code in range(0x110000) if unicodedata.category(chr(code)) == "Cf"), None
) | {ord("\u02dc"): " "}
# A note's sentence on its own, which no affiliation starts like and says: "This work was
# done when the author was at Adobe Research" (2609.00591), "Manuscript received August 9,
# 2021; ..." (2207.09313), "The authors worked as Independent Researchers" (2003.06975).
# Its second word is lowercase: "Supported Intelligence Lab" is a name.
_NOTE_SENTENCE_RE = re.compile(rf"^(?:{_NEXT_SENTENCE_STARTS}|The\s+authors?)\s+[a-z]")
# What a sentence of a thanks note says, and a list of affiliations does not: "Work done
# while A was a visiting student", "This work was supported by the X Foundation", "Now at".
_SENTENCE_WORD_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|has|have|had|work(?:ed|s)?|done|while|supported|funded"
    r"|grants?|projects?|contribut\w*|correspond\w*|equal\w*|e-?mail|thanks?|acknowledg\w*"
    r"|submitted|accepted|published|copyright|now)\b",
    re.IGNORECASE,
)
# What a symbol's note says of its people, and an affiliation does not: "‡Intern", "§Team lead".
_ROLE_RE = re.compile(
    r"\b(?:interns?|lead(?:er)?s?|advis\w*|supervis\w*|students?|authors?|mentors?)\b", re.IGNORECASE
)
# A web domain alone, whose "lab" is no laboratory: "jzlab.org" (2610.00751).
_DOMAIN_RE = re.compile(r"[\w-]+(?:\.[\w-]+)+")
# Where a footnote's affiliations end: its correspondence sentence, after which it lists
# people and addresses ("¹University of Tübingen. ²KAIST AI. Correspondence to Ankit
# Sonthalia <...>.", ICML's notice, 2610.35857), its mark perhaps before ("🖂 Corresponding
# Authors.", 2609.23796).
_CORRESPONDENCE_RE = re.compile(
    r"(?:^|(?<=[.;:]))\s*\W?\s*Correspond(?:ence|ing)\b.*", re.IGNORECASE | re.DOTALL
)
