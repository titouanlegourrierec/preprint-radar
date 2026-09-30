import { fold } from "./search";
import type { Paper } from "./types";

export type NodeKind = "paper" | "institution" | "author";
/** The kinds that gather papers, as opposed to the papers themselves. */
export type EntityKind = Exclude<NodeKind, "paper">;

export interface GraphNode {
  /** Stable identifier: kind + normalized name (or arXiv id for papers). */
  id: string;
  kind: NodeKind;
  /** Name, or title for papers. */
  label: string;
  /** The label as returned by {@link searchKey}, for highlighting by name. */
  key: string;
  /** Identifiers of the papers the node appears in (the paper itself for papers). */
  paperIds: string[];
}

export interface GraphLink {
  source: string;
  target: string;
  /** Number of papers shared by the two nodes. */
  weight: number;
}

export interface GraphOptions {
  papers: boolean;
  institutions: boolean;
  authors: boolean;
  /** Minimum number of papers for an institution or author to be shown. */
  minPapers: Record<EntityKind, number>;
  /** Whether to keep nodes without any link to another shown node. */
  isolated: boolean;
  /** Cap on the number of institutions and authors, keeping the most frequent ones. */
  maxNodes: number;
}

export interface Graph {
  /** Most frequent first. */
  nodes: GraphNode[];
  links: GraphLink[];
  /** Whether nodes were dropped because of `maxNodes`. */
  truncated: boolean;
}

// Words that identify the institution itself, as opposed to one of its departments or
// its address. Scores: 3 = university-like, 2 = organization, 1 = anything else.
const UNIVERSITY_RE =
  /universit|université|universität|universidad|università|polytechn|politecnico|college|academy|école|ecole|\b(?:eth|epfl|kaist|mit|inria|cnrs|riken|max planck)\b/i;
const ORGANIZATION_RE =
  /\b(?:inc|ltd|llc|gmbh|corp|corporation|company|labs?|laborator(?:y|ies)|research|institute|institut|centre|center|hospital|foundation|google|deepmind|meta|microsoft|nvidia|amazon|apple|adobe|tencent|alibaba|bytedance|baidu|huawei|samsung|sony|intel|openai|ibm|qualcomm)\b/i;
const UNIT_RE =
  /^(?:the\s+)?(?:dept\.?|department|school|faculty|division|chair|group|graduate school|key laboratory|state key laboratory)\b/i;

function segmentScore(segment: string): number {
  if (UNIT_RE.test(segment)) return 0.5;
  if (UNIVERSITY_RE.test(segment)) return 3;
  if (ORGANIZATION_RE.test(segment)) return 2;
  return 1;
}

/**
 * Institution named by an affiliation string, so that variants of the same institution
 * share a node: "Google, Switzerland" and "Google" both give "Google", and
 * "School of Computer Science, Peking University" gives "Peking University".
 * This is a heuristic; unusual formats may still produce separate nodes.
 */
export function institutionName(affiliation: string): string {
  const segments = affiliation
    .split(/[,;]/)
    .map((segment) => segment.trim().replace(/^the\s+/i, ""))
    // A lone "and" can be left over by the HTML extraction of older data.
    .filter((segment) => /\p{L}{2}/u.test(segment) && !/^and$/i.test(segment));
  let best = segments[0] ?? "";
  let bestScore = -1;
  for (const segment of segments) {
    const score = segmentScore(segment);
    if (score > bestScore) {
      best = segment;
      bestScore = score;
    }
  }
  return best;
}

/** Name normalized for comparison: folded, punctuation collapsed to single spaces. */
export function searchKey(text: string): string {
  return fold(text)
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function nodeKey(kind: EntityKind, label: string): string {
  return `${kind}:${searchKey(label)}`;
}

/** Whether the node's name contains `key` (as returned by {@link searchKey}). */
export function nodeMatches(node: GraphNode, key: string): boolean {
  return key !== "" && node.key.includes(key);
}

interface PaperAuthor {
  key: string;
  /** Indices into the paper's affiliations, `null` when the paper does not place them. */
  mapped: number[] | null;
}

/** A paper's institutions and authors, as node ids. */
interface PaperEntities {
  paper: Paper;
  /** Distinct institutions, in order. */
  institutions: string[];
  /** Node id of each affiliation, `null` when it names no institution. */
  keyOfAffiliation: (string | null)[];
  authors: PaperAuthor[];
}

export type EntityNode = GraphNode & { kind: EntityKind };

/** Whether the node gathers papers (an institution or an author), rather than being one. */
export function isEntity(node: GraphNode): node is EntityNode {
  return node.kind !== "paper";
}
type AddLink = (a: string, b: string) => void;

/**
 * Build the graph of the papers' institutions and authors.
 *
 * With papers shown, papers are the nodes everything hangs from: a paper is linked to
 * its authors, and each of its institutions to the shown authors the paper places there
 * (`author_affiliations`), or to the paper itself when it places none of them. Without
 * papers, the graph is their projection: institutions are linked when they share a
 * paper, authors when they co-sign one, and an author to their own institutions (all of
 * the paper's when it does not say who is where).
 */
export function buildGraph(papers: Paper[], options: GraphOptions): Graph {
  const nodes = new Map<string, EntityNode>();
  const labelCounts = new Map<string, Map<string, number>>();
  const perPaper: PaperEntities[] = [];

  const register = (kind: EntityKind, label: string, paperId: string, seen: Set<string>) => {
    const id = nodeKey(kind, label);
    if (id.endsWith(":")) return null;
    if (seen.has(id)) return { id, first: false };
    seen.add(id);
    const node = nodes.get(id) ?? { id, kind, label, key: "", paperIds: [] };
    node.paperIds.push(paperId);
    nodes.set(id, node);
    // Remember spellings to display the most frequent one.
    const counts = labelCounts.get(id) ?? new Map<string, number>();
    counts.set(label, (counts.get(label) ?? 0) + 1);
    labelCounts.set(id, counts);
    return { id, first: true };
  };

  for (const paper of papers) {
    const seen = new Set<string>();
    const institutions: string[] = [];
    const keyOfAffiliation: (string | null)[] = [];
    if (options.institutions) {
      for (const affiliation of paper.affiliations ?? []) {
        const entry = register("institution", institutionName(affiliation), paper.arxiv_id, seen);
        keyOfAffiliation.push(entry?.id ?? null);
        if (entry?.first) institutions.push(entry.id);
      }
    }
    const authors: PaperAuthor[] = [];
    if (options.authors) {
      for (const [position, author] of paper.authors.entries()) {
        const entry = register("author", author, paper.arxiv_id, seen);
        if (entry?.first) {
          authors.push({ key: entry.id, mapped: paper.author_affiliations?.[position] ?? null });
        }
      }
    }
    perPaper.push({ paper, institutions, keyOfAffiliation, authors });
  }

  for (const [id, counts] of labelCounts) {
    const node = nodes.get(id);
    if (node) node.label = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? node.label;
  }
  for (const node of nodes.values()) node.key = searchKey(node.label);

  const eligible = [...nodes.values()]
    .filter((node) => node.paperIds.length >= options.minPapers[node.kind])
    .sort((a, b) => b.paperIds.length - a.paperIds.length || a.label.localeCompare(b.label));
  const kept: GraphNode[] = eligible.slice(0, options.maxNodes);
  const keptIds = new Set(kept.map((node) => node.id));

  const weights = new Map<string, number>();
  const addLink: AddLink = (a, b) => {
    const key = a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
    weights.set(key, (weights.get(key) ?? 0) + 1);
  };
  const paperNodes = options.papers ? linkThroughPapers(perPaper, keptIds, addLink) : [];
  if (!options.papers) linkByCoOccurrence(perPaper, keptIds, addLink);

  const linked = new Set<string>();
  const links = [...weights].map(([key, weight]) => {
    const [source = "", target = ""] = key.split("\u0000");
    linked.add(source).add(target);
    return { source, target, weight };
  });

  const shown = [...kept, ...paperNodes];
  return {
    nodes: options.isolated ? shown : shown.filter((node) => linked.has(node.id)),
    links,
    truncated: eligible.length > kept.length,
  };
}

/** Link each paper to its shown authors, and its institutions to their authors or itself. */
function linkThroughPapers(
  perPaper: PaperEntities[],
  keptIds: ReadonlySet<string>,
  addLink: AddLink,
): GraphNode[] {
  return perPaper.map(({ paper, keyOfAffiliation, authors }) => {
    const id = `paper:${paper.arxiv_id}`;
    const shownAuthors = authors.filter((author) => keptIds.has(author.key));
    for (const author of shownAuthors) addLink(id, author.key);
    // Never hang an institution from an author the paper does not place there.
    const holders = new Map<string, Set<string>>();
    for (const [position, institution] of keyOfAffiliation.entries()) {
      if (institution === null || !keptIds.has(institution)) continue;
      const placed = holders.get(institution) ?? new Set<string>();
      holders.set(institution, placed);
      for (const author of shownAuthors) {
        if (author.mapped?.includes(position)) placed.add(author.key);
      }
    }
    for (const [institution, placed] of holders) {
      if (placed.size === 0) addLink(id, institution);
      for (const author of placed) addLink(author, institution);
    }
    return {
      id,
      kind: "paper",
      label: paper.title,
      key: searchKey(paper.title),
      paperIds: [paper.arxiv_id],
    };
  });
}

/** Link institutions sharing a paper, co-authors, and authors to their institutions. */
function linkByCoOccurrence(
  perPaper: PaperEntities[],
  keptIds: ReadonlySet<string>,
  addLink: AddLink,
): void {
  for (const { institutions, keyOfAffiliation, authors } of perPaper) {
    const inst = institutions.filter((id) => keptIds.has(id));
    for (let i = 0; i < inst.length; i++) {
      for (let j = i + 1; j < inst.length; j++) addLink(inst[i] ?? "", inst[j] ?? "");
    }
    const auth = authors.filter((author) => keptIds.has(author.key));
    for (let i = 0; i < auth.length; i++) {
      for (let j = i + 1; j < auth.length; j++) addLink(auth[i]?.key ?? "", auth[j]?.key ?? "");
    }
    for (const { key, mapped } of auth) {
      const own =
        mapped === null
          ? inst
          : [
              ...new Set(
                mapped
                  .map((index) => keyOfAffiliation[index])
                  .filter((id): id is string => typeof id === "string" && keptIds.has(id)),
              ),
            ];
      for (const target of own) addLink(key, target);
    }
  }
}
