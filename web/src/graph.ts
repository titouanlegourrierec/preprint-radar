import { institutionsOf } from "./institutions";
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
  // Per author node, its Semantic Scholar profiles, and where and with whom they publish.
  const profiles = new Map<string, Map<string, Profile>>();
  const perPaper: PaperEntities[] = [];
  const citationsOf = (paperId: string) => options.citations?.get(paperId) ?? 0;

  const register = (kind: EntityKind, label: string, paperId: string, seen: Set<string>) => {
    const id = nodeKey(kind, label);
    if (id.endsWith(":")) return null;
    if (seen.has(id)) return { id, first: false };
    seen.add(id);
    const node = nodes.get(id) ?? { id, kind, label, key: "", paperIds: [], citations: 0 };
    node.paperIds.push(paperId);
    node.citations += citationsOf(paperId);
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
      for (const [position, author] of paper.authors.entries()) {
        const entry = register("author", author, paper.arxiv_id, seen);
        if (entry?.first) authors.push({ key: entry.id, mapped: mapping?.[position] ?? null });
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
  const paperNodes = options.papers
    ? linkThroughPapers(perPaper, keptIds, addLink, citationsOf)
    : [];
  const consortia = options.papers ? 0 : linkByCoOccurrence(perPaper, keptIds, addLink);

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
    consortia,
  };
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
  citationsOf: (paperId: string) => number,
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
      citations: citationsOf(paper.arxiv_id),
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
  const matches = `${count.toLocaleString()} ${count === 1 ? "match" : "matches"}`;
  if (index === null) return `${matches}: Enter shows them one by one, Shift+Enter backwards`;
  return `${(index + 1).toLocaleString()} of ${matches}${label ? `: ${label}` : ""}`;
}
