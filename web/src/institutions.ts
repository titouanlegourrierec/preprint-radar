import { searchKey } from "./text";
import type { Paper } from "./types";

// Words that identify the institution itself, as opposed to one of its departments or
// its address. Scores: 3 = university-like, 2 = organization, 1 = anything else,
// 0.5 = a unit of some institution, 0.25 = an address.
const UNIVERSITY_RE =
  /universit|université|universität|universidad|università|polytechn|politecnico|college|academy|école|ecole|\b(?:eth|epfl|kaist|mit|inria|cnrs|riken|max planck)\b/i;
const ORGANIZATION_RE =
  /\b(?:inc|ltd|llc|gmbh|corp|corporation|company|labs?|laborator(?:y|ies)|research|institute|institut|centre|center|hospital|foundation|google|deepmind|meta|microsoft|nvidia|amazon|apple|adobe|tencent|alibaba|bytedance|baidu|huawei|samsung|sony|intel|openai|ibm|qualcomm)\b/i;
const UNIT_RE =
  /^(?:the\s+)?(?:dept\.?|department|school|faculty|division|chair|group|graduate school|college of|laboratory of|key laboratory|state key laboratory)\b/i;
// "Zhiyang Innovation Co., Ltd.": the legal suffix belongs to the name before it.
const LEGAL_SUFFIX_RE = /,\s*(ltd|inc|llc|gmbh|co|corp|ag|plc|s\.a|s\.r\.l)\b/gi;
// "A and B are with the University of X": only the institution matters.
const ARE_WITH_RE = /^.*?\b(?:is|are)\s+(?:also\s+)?(?:with|at)\s+/i;
// Not an institution at all: people who work on their own.
const INDEPENDENT_RE =
  /^(?:an?\s+)?(?:independent|individual)(?:\s+(?:researcher|scholar|scientist|author)s?)?$/i;
// Not an affiliation either, in data extracted before the pipeline rejected them (as
// `_JUNK_RE` in arxiv_html.py does): link labels, contribution notes, lone words, a country.
const JUNK_RE =
  /^(?:the|an?|dot|code|github|data(?:set)?|demo|video|website|homepage|graduate|correspondence|project\s+(?:page|website)|(?:core\s+|main\s+)?contributors?|(?:co-?)?(?:first|second|last|senior)\s+authors?)$/i;
const COUNTRY_RE =
  /^(?:USA|U\.S\.A?\.?|United States(?: of America)?|UK|U\.K\.|United Kingdom|England|Scotland|(?:P\.?\s?R\.?\s?)?China|Hong Kong(?: SAR)?|Macau|Macao|Taiwan|Japan|(?:South |Republic of )?Korea|Singapore|India|Germany|France|Italy|Spain|Portugal|(?:The )?Netherlands|Belgium|Switzerland|Austria|Sweden|Norway|Denmark|Finland|Ireland|Poland|Czech Republic|Czechia|Hungary|Romania|Greece|Cyprus|Turkey|Türkiye|Israel|Iran|Saudi Arabia|United Arab Emirates|UAE|Qatar|Egypt|Morocco|Nigeria|South Africa|Canada|Mexico|Brazil|Chile|Argentina|Colombia|Peru|Ecuador|Australia|New Zealand|Russia|Ukraine|Vietnam|Viet Nam|Thailand|Malaysia|Indonesia|Philippines|Pakistan|Bangladesh|Luxembourg)\.?$/i;
// Companies are written many ways ("NVIDIA AI Technology Centre", "Microsoft Research
// Asia", "ARC Lab, Tencent IEG"): any mention names the company. Hospitals named after
// a company ("Samsung Medical Center") are not the company.
const BRANDS: readonly (readonly [RegExp, string])[] = [
  [/\bdeepmind\b/i, "Google DeepMind"],
  [/\bgoogle\b/i, "Google"],
  [/\bnvidia\b/i, "NVIDIA"],
  [/\b(?:meta|facebook)\b/i, "Meta"],
  [/\bmicrosoft\b/i, "Microsoft"],
  [/\btencent\b/i, "Tencent"],
  [/\badobe\b/i, "Adobe"],
  [/\bhuawei\b/i, "Huawei"],
  [/\b(?:alibaba|damo academy)\b/i, "Alibaba Group"],
  [/\bbytedance\b/i, "ByteDance"],
  [/\bbaidu\b/i, "Baidu"],
  [/\bsamsung\b/i, "Samsung"],
  [/\bsony\b/i, "Sony"],
  [/\bamazon\b/i, "Amazon"],
  [/\bapple\b/i, "Apple"],
  [/\bintel\b/i, "Intel"],
  [/\bqualcomm\b/i, "Qualcomm"],
  [/\bibm\b/i, "IBM"],
  [/\bopenai\b/i, "OpenAI"],
  [/\bxiaomi\b/i, "Xiaomi"],
  [/\bkuaishou\b/i, "Kuaishou"],
  [/\bsensetime\b/i, "SenseTime"],
];
const NOT_A_BRAND_RE = /hospital|medical|clinic/i;
// Acronyms written alone, mapped to the names the Research Organization Registry (ROR)
// gives, so that they share a node with the full names it resolves. Keys are search
// keys; ambiguous ones (NTU: Nanyang or National Taiwan) are left out.
const ACRONYMS: Readonly<Record<string, string>> = {
  mit: "Massachusetts Institute of Technology",
  cmu: "Carnegie Mellon University",
  kaist: "Korea Advanced Institute of Science and Technology",
  kaust: "King Abdullah University of Science and Technology",
  hust: "Huazhong University of Science and Technology",
  ustc: "University of Science and Technology of China",
  sjtu: "Shanghai Jiao Tong University",
  zju: "Zhejiang University",
  pku: "Peking University",
  thu: "Tsinghua University",
  cuhk: "Chinese University of Hong Kong",
  cuhksz: "Chinese University of Hong Kong, Shenzhen",
  "cuhk sz": "Chinese University of Hong Kong, Shenzhen",
  "cuhk shenzhen": "Chinese University of Hong Kong, Shenzhen",
  hkust: "Hong Kong University of Science and Technology",
  hku: "University of Hong Kong",
  nus: "National University of Singapore",
  ucla: "University of California, Los Angeles",
  ucsd: "University of California, San Diego",
  ucl: "University College London",
  "uc san diego": "University of California, San Diego",
  "uc berkeley": "University of California, Berkeley",
  uiuc: "University of Illinois Urbana-Champaign",
  epfl: "École Polytechnique Fédérale de Lausanne",
  tum: "Technical University of Munich",
  eth: "ETH Zurich",
  ethz: "ETH Zurich",
  ucas: "University of Chinese Academy of Sciences",
  bupt: "Beijing University of Posts and Telecommunications",
  sustech: "Southern University of Science and Technology",
  uestc: "University of Electronic Science and Technology of China",
  xjtu: "Xi'an Jiaotong University",
  nju: "Nanjing University",
  hit: "Harbin Institute of Technology",
  bit: "Beijing Institute of Technology",
  "georgia tech": "Georgia Institute of Technology",
  caltech: "California Institute of Technology",
  casia: "Chinese Academy of Sciences",
};
// Campuses of the University of California, written as a separate segment.
const UC_CAMPUS_RE =
  /^(?:berkeley|los angeles|san diego|davis|irvine|santa barbara|santa cruz|riverside|merced|san francisco)$/i;

function segmentScore(segment: string): number {
  if (UNIT_RE.test(segment)) return 0.5;
  if (UNIVERSITY_RE.test(segment)) return 3;
  // Postcodes and street numbers: an address, unless nothing better is written.
  if (/\d/.test(segment)) return 0.25;
  if (ORGANIZATION_RE.test(segment)) return 2;
  return 1;
}

/**
 * Institution named by an affiliation string, so that variants of the same institution
 * share a node: "Google, Switzerland" and "Google" both give "Google", "School of
 * Computer Science, Peking University" gives "Peking University", "CMU" gives "Carnegie
 * Mellon University". Returns "" when the string names no institution: a department on
 * its own, an address, an independent researcher. This is a heuristic; unusual formats
 * may still produce separate nodes.
 */
export function institutionName(affiliation: string): string {
  const segments = affiliation
    .replace(LEGAL_SUFFIX_RE, " $1")
    .replace(ARE_WITH_RE, "")
    .split(/[,;]/)
    .map((segment) => segment.trim().replace(/^the\s+/i, ""))
    // A lone "and" can be left over by the HTML extraction of older data.
    .filter((segment) => /\p{L}{2}/u.test(segment) && !/^and$/i.test(segment))
    .filter(
      (segment) =>
        !INDEPENDENT_RE.test(segment) && !JUNK_RE.test(segment) && !COUNTRY_RE.test(segment),
    );
  let best = "";
  let bestIndex = -1;
  let bestScore = -1;
  for (const [index, segment] of segments.entries()) {
    const alias = ACRONYMS[searchKey(segment)];
    if (alias) return alias;
    const score = segmentScore(segment);
    if (score > bestScore) {
      best = segment;
      bestIndex = index;
      bestScore = score;
    }
  }
  if (bestScore < 3) {
    for (const [pattern, brand] of BRANDS) {
      if (segments.some((segment) => pattern.test(segment) && !NOT_A_BRAND_RE.test(segment))) {
        return brand;
      }
    }
  }
  if (bestScore <= 0.5) return "";
  const next = segments[bestIndex + 1];
  if (/^university of california$/i.test(best) && next !== undefined && UC_CAMPUS_RE.test(next)) {
    return `${best}, ${next}`;
  }
  return best;
}

/**
 * The institution an acronym stands for ("NUS" is National University of Singapore), as
 * the graph names it; `null` for anything else.
 */
export function acronymOf(text: string): string | null {
  return ACRONYMS[searchKey(text)] ?? null;
}

/**
 * The name to give a company as ROR spells it ("Microsoft Research Asia"), so that it
 * shares a node with the other ways the company is written.
 */
export function canonicalInstitution(name: string): string {
  for (const [pattern, brand] of BRANDS) {
    if (pattern.test(name) && !NOT_A_BRAND_RE.test(name)) return brand;
  }
  return name;
}

/**
 * The institution of each of the paper's affiliations, in order: the one the pipeline
 * found in the Research Organization Registry when there is one, else
 * {@link institutionName}. An empty string means that the affiliation names none.
 */
export function paperInstitutions(paper: Paper): string[] {
  const affiliations = paper.affiliations ?? [];
  const registry = paper.institutions?.length === affiliations.length ? paper.institutions : null;
  return affiliations.map((affiliation, index) => {
    const found = registry?.[index];
    return found ? canonicalInstitution(found) : institutionName(affiliation);
  });
}

/**
 * The institution of each of the paper's affiliations as the graph and Rankings count
 * them: {@link paperInstitutions}, with `null` for an affiliation that names none, or that
 * names one of the paper's own authors (a person is not an institution). The exact
 * affiliation filter matches these, so that a clicked row shows as many papers as it says.
 */
export function institutionsOf(paper: Paper): (string | null)[] {
  const people = new Set(paper.authors.map(searchKey));
  return paperInstitutions(paper).map((name) => {
    const key = searchKey(name);
    return key === "" || people.has(key) ? null : name;
  });
}
