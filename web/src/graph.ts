import { fold } from "./search";
import type { Paper } from "./types";

export type NodeKind = "institution" | "author";

export interface GraphNode {
  /** Stable identifier: kind + normalized name. */
  id: string;
  kind: NodeKind;
  label: string;
  /** Identifiers of the papers the node appears in. */
  paperIds: string[];
}

export interface GraphLink {
  source: string;
  target: string;
  /** Number of papers shared by the two nodes. */
  weight: number;
}

export interface GraphOptions {
  institutions: boolean;
  authors: boolean;
  /** Minimum number of papers for a node of each kind to be shown. */
  minPapers: Record<NodeKind, number>;
  /** Whether to keep nodes that share no paper with any other shown node. */
  isolated: boolean;
  /** Cap on the number of nodes, keeping the most frequent ones (`Infinity`: no cap). */
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

function nodeKey(kind: NodeKind, label: string): string {
  return `${kind}:${searchKey(label)}`;
}

/** Whether the node's name contains `key` (as returned by {@link searchKey}). */
export function nodeMatches(node: GraphNode, key: string): boolean {
  return key !== "" && node.id.includes(key, node.kind.length + 1);
}

/** Build a co-occurrence graph: two nodes are linked when they appear on the same paper. */
export function buildGraph(papers: Paper[], options: GraphOptions): Graph {
  const nodes = new Map<string, GraphNode>();
  const labelCounts = new Map<string, Map<string, number>>();
  const paperNodes: string[][] = [];

  const add = (kind: NodeKind, label: string, paperId: string, keys: Set<string>) => {
    const id = nodeKey(kind, label);
    if (keys.has(id) || id.endsWith(":")) return;
    keys.add(id);
    const node = nodes.get(id) ?? { id, kind, label, paperIds: [] };
    node.paperIds.push(paperId);
    nodes.set(id, node);
    // Remember spellings to display the most frequent one.
    const counts = labelCounts.get(id) ?? new Map<string, number>();
    counts.set(label, (counts.get(label) ?? 0) + 1);
    labelCounts.set(id, counts);
  };

  for (const paper of papers) {
    const keys = new Set<string>();
    if (options.institutions) {
      for (const affiliation of paper.affiliations ?? []) {
        add("institution", institutionName(affiliation), paper.arxiv_id, keys);
      }
    }
    if (options.authors) {
      for (const author of paper.authors) add("author", author, paper.arxiv_id, keys);
    }
    paperNodes.push([...keys]);
  }

  for (const [id, counts] of labelCounts) {
    const node = nodes.get(id);
    if (node) node.label = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? node.label;
  }

  const eligible = [...nodes.values()]
    .filter((node) => node.paperIds.length >= options.minPapers[node.kind])
    .sort((a, b) => b.paperIds.length - a.paperIds.length || a.label.localeCompare(b.label));
  const kept = eligible.slice(0, options.maxNodes);
  const keptIds = new Set(kept.map((node) => node.id));

  const weights = new Map<string, number>();
  for (const keys of paperNodes) {
    const present = keys.filter((key) => keptIds.has(key)).sort();
    for (let i = 0; i < present.length; i++) {
      for (let j = i + 1; j < present.length; j++) {
        const pair = `${present[i]}\u0000${present[j]}`;
        weights.set(pair, (weights.get(pair) ?? 0) + 1);
      }
    }
  }
  const linked = new Set<string>();
  const links = [...weights].map(([pair, weight]) => {
    const [source = "", target = ""] = pair.split("\u0000");
    linked.add(source).add(target);
    return { source, target, weight };
  });

  return {
    nodes: options.isolated ? kept : kept.filter((node) => linked.has(node.id)),
    links,
    truncated: eligible.length > kept.length,
  };
}
