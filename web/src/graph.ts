import { acronymOf, institutionsOf } from "./institutions";
import { LOCALE } from "./locale";
import { searchKey } from "./text";
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
  /** Citations of those papers, summed; papers without a known count add nothing. */
  citations: number;
  /** An institution's id in the Research Organization Registry, when a paper gives it. */
  rorId?: string;
  /**
   * For an author: how many people the name seems to be, when more than one. Semantic
   * Scholar has several profiles for most prolific authors, so its ids do not key authors;
   * but profiles of one name whose papers share no institution and no co-author are
   * probably different people ({@link countPeople}, AFF-H, decision 13).
   */
  people?: number;
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
  /** Citation count of each paper, by arXiv id, when known. */
  citations?: ReadonlyMap<string, number>;
}

export interface Graph {
  /** Most frequent first. */
  nodes: GraphNode[];
  links: GraphLink[];
  /** Whether nodes were dropped because of `maxNodes`. */
  truncated: boolean;
  /** Institutions and authors with enough papers, before `maxNodes` keeps the first. */
  eligible: number;
  /** Papers whose authors are not linked to one another: more than `MAX_CLIQUE_AUTHORS`. */
  consortia: number;
}

/**
 * Above this many authors, a paper does not link its authors to one another in the
 * projection: every pair would be linked, n(n-1)/2, and those links say nothing about who
 * works with whom. One paper of 561 authors made 39% of the 397,000 links of the 2024
 * archive's author projection (PERF-3, decision 15). Their links to institutions stay.
 */
export const MAX_CLIQUE_AUTHORS = 50;

function nodeKey(kind: EntityKind, label: string): string {
  return `${kind}:${searchKey(label)}`;
}

/**
 * Where a name listed twice by a paper is placed: at the affiliations of either occurrence,
 * `null` when the paper places neither.
 */
function placedAtEither(a: number[] | null | undefined, b: number[] | null): number[] | null {
  if (!a) return b;
  if (!b) return a;
  return [...new Set([...a, ...b])];
}

/**
 * What a search of the graph finds: the nodes whose name contains `key` (as returned by
 * {@link searchKey}). A known acronym, as the affiliation filter reads it, finds its
 * institution however its node is named ("KAIST" finds Korea Advanced Institute of Science
 * and Technology) and the names holding it as a word: "MIT" is no part of "RMIT" nor
 * "Limited", "ETH" of "Goethe". Built once a search, for every node.
 */
export function nodeMatcher(key: string): (node: GraphNode) => boolean {
  if (key === "") return () => false;
  const institution = acronymOf(key);
  if (institution === null) return (node) => node.key.includes(key);
  const institutionKey = searchKey(institution);
  return (node) =>
    (node.kind === "institution" && node.key === institutionKey) ||
    ` ${node.key} `.includes(` ${key} `);
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
  // Per author node, its Semantic Scholar profiles, and where and with whom they publish.
  const profiles = new Map<string, Map<string, Profile>>();
  const perPaper: PaperEntities[] = [];

  const register = (kind: EntityKind, label: string, paperId: string, seen: Set<string>) => {
    const id = nodeKey(kind, label);
    if (id.endsWith(":")) return null;
    if (seen.has(id)) return { id, first: false };
    seen.add(id);
    const node = nodes.get(id) ?? { id, kind, label, key: "", paperIds: [], citations: 0 };
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
      for (const [index, name] of institutionsOf(paper).entries()) {
        const entry = name === null ? null : register("institution", name, paper.arxiv_id, seen);
        keyOfAffiliation.push(entry?.id ?? null);
        if (entry?.first) institutions.push(entry.id);
        const rorId = paper.institution_ids?.[index];
        const node = entry ? nodes.get(entry.id) : undefined;
        if (rorId && node) node.rorId ??= rorId;
      }
    }
    const authors: PaperAuthor[] = [];
    if (options.authors) {
      // The mapping is positional: one out of step with the authors places nobody.
      const mapping =
        paper.author_affiliations?.length === paper.authors.length
          ? paper.author_affiliations
          : null;
      const ids = paper.author_ids?.length === paper.authors.length ? paper.author_ids : null;
      const named = institutionsOf(paper);
      const keys = paper.authors.map((author) => searchKey(author));
      // A name the paper lists twice is one author, placed wherever either is (AFF-21).
      const placed = new Map<string, number[] | null>();
      for (const [position, author] of paper.authors.entries()) {
        const entry = register("author", author, paper.arxiv_id, seen);
        const mapped = mapping?.[position] ?? null;
        if (entry) placed.set(entry.id, placedAtEither(placed.get(entry.id), mapped));
        const id = ids?.[position];
        if (!entry || !id) continue;
        const profile = profilesOf(profiles, entry.id, id);
        profile.papers += 1;
        for (const index of mapping?.[position] ?? []) {
          const institution = named[index];
          if (institution) profile.institutions.add(institution);
        }
        for (const [other, key] of keys.entries())
          if (other !== position) profile.coauthors.add(key);
      }
      for (const [key, mapped] of placed) authors.push({ key, mapped });
    }
    perPaper.push({ paper, institutions, keyOfAffiliation, authors });
  }

  for (const [id, counts] of labelCounts) {
    const node = nodes.get(id);
    if (node) node.label = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? node.label;
  }
  for (const node of nodes.values()) node.key = searchKey(node.label);
  for (const [id, byProfile] of profiles) {
    const people = countPeople([...byProfile.values()]);
    const node = nodes.get(id);
    if (node && people > 1) node.people = people;
  }

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
  const consortia = options.papers ? 0 : linkByCoOccurrence(perPaper, keptIds, addLink);

  const linked = new Set<string>();
  const links = [...weights].map(([key, weight]) => {
    const [source = "", target = ""] = key.split("\u0000");
    linked.add(source).add(target);
    return { source, target, weight };
  });

  const shown = [...kept, ...paperNodes];
  const graph = {
    nodes: options.isolated ? shown : shown.filter((node) => linked.has(node.id)),
    links,
    truncated: eligible.length > kept.length,
    eligible: eligible.length,
    consortia,
  };
  return options.citations ? withCitations(graph, options.citations) : graph;
}

/**
 * The graph with the citations of each node's papers, summed (a paper without a known
 * count adds nothing): new nodes, the same links. The graph view builds its graph without
 * counts and adds them apart, so that counts arriving once it is laid out size its nodes
 * again rather than build and lay it out anew (PERF-7).
 */
export function withCitations(graph: Graph, citations: ReadonlyMap<string, number>): Graph {
  return {
    ...graph,
    nodes: graph.nodes.map((node) => ({
      ...node,
      citations: node.paperIds.reduce((sum, id) => sum + (citations.get(id) ?? 0), 0),
    })),
  };
}

/**
 * Whether two graphs lay out alike: the same nodes in the same order, and the same links
 * with the same weights. What the nodes say (their citations) may differ.
 */
export function sameLayout(a: Graph, b: Graph): boolean {
  return (
    a.nodes.length === b.nodes.length &&
    a.links.length === b.links.length &&
    a.nodes.every((node, index) => node.id === b.nodes[index]?.id) &&
    a.links.every((link, index) => {
      const other = b.links[index];
      return (
        other !== undefined &&
        link.source === other.source &&
        link.target === other.target &&
        link.weight === other.weight
      );
    })
  );
}

/** What the site says of a name that seems to be several people. */
export function severalPeople(people: number): string {
  return (
    `Perhaps ${people} people share this name: Semantic Scholar's profiles of it fall into ` +
    `${people} groups whose papers here share no institution and no co-author. Their papers ` +
    "are counted together."
  );
}

/** A Semantic Scholar profile of a name: where its papers place it, and its co-authors. */
export interface Profile {
  institutions: Set<string>;
  coauthors: Set<string>;
  papers: number;
}

/**
 * Papers a group of profiles needs to count as a person: a profile of one paper is often
 * an orphan duplicate, without an institution to tie it to the others (1,304 names of the
 * store seem to be several people so, 5,967 counting those).
 */
export const PERSON_PAPERS = 2;

function profilesOf(
  profiles: Map<string, Map<string, Profile>>,
  node: string,
  id: string,
): Profile {
  const byProfile = profiles.get(node) ?? new Map<string, Profile>();
  profiles.set(node, byProfile);
  const profile = byProfile.get(id) ?? { institutions: new Set(), coauthors: new Set(), papers: 0 };
  byProfile.set(id, profile);
  return profile;
}

/**
 * How many people a name's profiles seem to be: profiles that share an institution or a
 * co-author are one person (the same person's duplicates), and those left apart are others,
 * with at least {@link PERSON_PAPERS} papers.
 * Luc Van Gool's three profiles share ETH Zurich; two Wei Wangs, at Tsinghua and at
 * Zhejiang with no co-author in common, are two.
 */
export function countPeople(profiles: readonly Profile[]): number {
  const parent = profiles.map((_, index) => index);
  const root = (index: number): number => {
    let at = index;
    while (parent[at] !== at) at = parent[at] ?? at;
    return at;
  };
  const shares = (a: Set<string>, b: Set<string>) => [...a].some((value) => b.has(value));
  for (const [i, a] of profiles.entries()) {
    for (const [j, b] of profiles.entries()) {
      if (j <= i) continue;
      if (shares(a.institutions, b.institutions) || shares(a.coauthors, b.coauthors)) {
        parent[root(j)] = root(i);
      }
    }
  }
  const papers = new Map<number, number>();
  for (const [index, profile] of profiles.entries()) {
    papers.set(root(index), (papers.get(root(index)) ?? 0) + profile.papers);
  }
  return [...papers.values()].filter((count) => count >= PERSON_PAPERS).length;
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
      citations: 0,
    };
  });
}

/**
 * Link institutions sharing a paper, co-authors, and authors to their institutions.
 *
 * @returns The number of papers with authors shown whose authors were not linked to one
 *   another, having more than {@link MAX_CLIQUE_AUTHORS}.
 */
function linkByCoOccurrence(
  perPaper: PaperEntities[],
  keptIds: ReadonlySet<string>,
  addLink: AddLink,
): number {
  let consortia = 0;
  for (const { paper, institutions, keyOfAffiliation, authors } of perPaper) {
    const inst = institutions.filter((id) => keptIds.has(id));
    for (let i = 0; i < inst.length; i++) {
      for (let j = i + 1; j < inst.length; j++) addLink(inst[i] ?? "", inst[j] ?? "");
    }
    const auth = authors.filter((author) => keptIds.has(author.key));
    if (paper.authors.length > MAX_CLIQUE_AUTHORS) {
      if (auth.length > 1) consortia++;
    } else {
      for (let i = 0; i < auth.length; i++) {
        for (let j = i + 1; j < auth.length; j++) addLink(auth[i]?.key ?? "", auth[j]?.key ?? "");
      }
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
  return consortia;
}

/** The time-lapse stops at most this many times: a year of days would take minutes. */
export const MAX_REPLAY_STEPS = 60;

/**
 * The days a time-lapse stops at, in order: every day, or else the last day of each week,
 * or else of each month. An archive year has about 340 days, 5 minutes of a layout that
 * never settles (PERF-2).
 */
export function replaySteps(days: readonly string[]): string[] {
  if (days.length <= MAX_REPLAY_STEPS) return [...days];
  const weekly = lastOfEach(days, weekOf);
  return weekly.length <= MAX_REPLAY_STEPS ? weekly : lastOfEach(days, (day) => day.slice(0, 7));
}

/** The last day of each group of consecutive sorted days. */
function lastOfEach(days: readonly string[], group: (day: string) => string): string[] {
  const last = new Map<string, string>();
  for (const day of days) last.set(group(day), day);
  return [...last.values()];
}

/** The Monday of a day's week (ISO dates). */
function weekOf(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
}

/** What the graph's Highlight field found, and which match is shown (`label`, at `index`). */
export function matchStatus(count: number, index: number | null, label: string | null): string {
  if (count === 0) return "No match";
  const matches = `${count.toLocaleString(LOCALE)} ${count === 1 ? "match" : "matches"}`;
  if (index === null) return `${matches}: Enter shows them one by one, Shift+Enter backwards`;
  return `${(index + 1).toLocaleString(LOCALE)} of ${matches}${label ? `: ${label}` : ""}`;
}

/** The papers two nodes share: what MIT and Google wrote together (§17.1 #8). */
export function sharedPapers(a: GraphNode, b: GraphNode): string[] {
  const other = new Set(b.paperIds);
  return a.paperIds.filter((id) => other.has(id));
}

/**
 * The papers a link stands for, as its weight counts them. With papers as nodes, two
 * entities share a paper when both are on it ({@link sharedPapers}); in the projection, a
 * paper links them only as {@link buildGraph} does: an author to their own institutions,
 * co-authors of up to {@link MAX_CLIQUE_AUTHORS}. Whether a paper links two nodes depends
 * on that paper alone, so the graph of each shared paper alone tells: few, built on demand.
 */
export function linkPapers(
  a: GraphNode,
  b: GraphNode,
  papers: ReadonlyMap<string, Paper>,
  options: GraphOptions,
): string[] {
  const shared = sharedPapers(a, b);
  if (options.papers) return shared;
  const single: GraphOptions = {
    ...options,
    minPapers: { institution: 1, author: 1 },
    maxNodes: Number.POSITIVE_INFINITY,
    isolated: true,
  };
  return shared.filter((id) => {
    const paper = papers.get(id);
    return (
      paper !== undefined &&
      buildGraph([paper], single).links.some(
        (link) =>
          (link.source === a.id && link.target === b.id) ||
          (link.source === b.id && link.target === a.id),
      )
    );
  });
}

/**
 * A node id as `buildGraph` keys nodes: a link written by hand ("institution:MIT") is the
 * node "institution:mit"; a paper's id is its arXiv id, which a search key would break.
 */
export function canonicalNodeId(id: string): string {
  const separator = id.indexOf(":");
  const kind = id.slice(0, separator);
  return kind === "institution" || kind === "author"
    ? `${kind}:${searchKey(id.slice(separator + 1))}`
    : id;
}

/**
 * The papers of a node, by its id (`institution:<key>`, `author:<key>`, `paper:<id>`):
 * the graph of these alone is the node's ego network, "Focus on this" (§17.1 #8), with
 * whom an institution or an author publishes. Matched as {@link buildGraph} keys nodes, so
 * that the node keeps all its papers.
 */
export function papersOfNode(papers: readonly Paper[], id: string): Paper[] {
  const separator = id.indexOf(":");
  const kind = id.slice(0, separator);
  const name = id.slice(separator + 1);
  // A link written by hand ("institution:MIT") means the node keyed "institution:mit".
  const key = searchKey(name);
  switch (kind) {
    case "paper":
      return papers.filter((paper) => paper.arxiv_id === name);
    case "institution":
      return papers.filter((paper) =>
        institutionsOf(paper).some((name) => name !== null && searchKey(name) === key),
      );
    case "author":
      return papers.filter((paper) => paper.authors.some((author) => searchKey(author) === key));
    default:
      return [];
  }
}

/**
 * A node's name among papers, its most frequent spelling as {@link buildGraph} names it:
 * for a node the graph does not draw (filtered out, or a focus without papers left),
 * rather than its lowercased key. `null` when no paper names it.
 */
export function nodeLabel(papers: readonly Paper[], id: string): string | null {
  const separator = id.indexOf(":");
  const kind = id.slice(0, separator);
  const key = searchKey(id.slice(separator + 1));
  const counts = new Map<string, number>();
  for (const paper of papers) {
    const names =
      kind === "institution"
        ? institutionsOf(paper).filter((name): name is string => name !== null)
        : kind === "author"
          ? paper.authors
          : [];
    for (const name of new Set(names)) {
      if (searchKey(name) === key) counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null;
}

/** A node's connection in its details: another node, and the papers their link counts. */
export interface Connection {
  node: GraphNode;
  weight: number;
}

/** The institutions and authors of each paper, when papers are nodes themselves. */
export function entitiesByPaper(graph: Graph): Map<string, GraphNode[]> {
  const byPaper = new Map<string, GraphNode[]>();
  for (const node of graph.nodes) {
    if (node.kind === "paper") continue;
    for (const id of node.paperIds) byPaper.set(id, [...(byPaper.get(id) ?? []), node]);
  }
  return byPaper;
}

/**
 * A node's most connected nodes, the strongest `limit` first: with papers as nodes (given
 * `entities`, from {@link entitiesByPaper}), the entities it shares papers with; in the
 * projection, the nodes its links reach, by their weight.
 */
export function nodeConnections(
  graph: Graph,
  node: GraphNode,
  entities: ReadonlyMap<string, GraphNode[]> | null,
  limit: number,
): Connection[] {
  let connections: Connection[];
  if (entities) {
    const shared = new Map<GraphNode, number>();
    for (const id of node.paperIds) {
      for (const other of entities.get(id) ?? []) {
        if (other !== node) shared.set(other, (shared.get(other) ?? 0) + 1);
      }
    }
    connections = [...shared].map(([other, weight]) => ({ node: other, weight }));
  } else {
    const byId = new Map(graph.nodes.map((entry) => [entry.id, entry]));
    connections = graph.links.flatMap((link) => {
      if (link.source !== node.id && link.target !== node.id) return [];
      const other = byId.get(link.source === node.id ? link.target : link.source);
      return other ? [{ node: other, weight: link.weight }] : [];
    });
  }
  return connections
    .sort((a, b) => b.weight - a.weight || b.node.paperIds.length - a.node.paperIds.length)
    .slice(0, limit);
}
