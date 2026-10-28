import { searchKey } from "./text";
import type { Paper } from "./types";

// Acronyms written alone, and the institution each stands for, as the pipeline names them
// (`ACRONYMS` in src/preprint_radar/institutions.py, which a test keeps equal): the search
// finds "NUS" in National University of Singapore's papers. Keys are search keys.
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
  "hkust gz": "Hong Kong University of Science and Technology (Guangzhou)",
  "hkust guangzhou": "Hong Kong University of Science and Technology (Guangzhou)",
  hku: "University of Hong Kong",
  nus: "National University of Singapore",
  ucla: "University of California, Los Angeles",
  ucsd: "University of California San Diego",
  ucl: "University College London",
  "uc san diego": "University of California San Diego",
  "uc berkeley": "University of California, Berkeley",
  ucb: "University of California, Berkeley",
  oxford: "University of Oxford",
  stanford: "Stanford University",
  harvard: "Harvard University",
  princeton: "Princeton University",
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

/**
 * The institution an acronym stands for ("NUS" is National University of Singapore), as
 * the pipeline names it; `null` for anything else.
 */
export function acronymOf(text: string): string | null {
  return ACRONYMS[searchKey(text)] ?? null;
}

/**
 * The institution of each of the paper's affiliations, in order, as the pipeline named
 * them: the Research Organization Registry's (or OpenAlex's), a company's subsidiaries as
 * the company, and its own rules for the rest (`src/preprint_radar/institutions.py`).
 * `null` for an affiliation that names none, and for every affiliation of a record not
 * named yet. The graph, Rankings and the affiliation filter all count these.
 */
export function institutionsOf(paper: Paper): (string | null)[] {
  const affiliations = paper.affiliations ?? [];
  const named = paper.institutions?.length === affiliations.length ? paper.institutions : null;
  return affiliations.map((_, index) => named?.[index] || null);
}

/** The institutions the paper's affiliations name, without the gaps. */
export function namedInstitutions(paper: Paper): string[] {
  return institutionsOf(paper).filter((name): name is string => name !== null);
}
