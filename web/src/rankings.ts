import { authorPeople, buildGraph, type EntityKind, isEntity } from "./graph";
import type { Paper } from "./types";

export type RankingMetric = "papers" | "citations";

/** An institution or an author, with what it published among the given papers. */
export interface RankedEntity {
  /** Stable identifier, the one of its graph node. */
  id: string;
  kind: EntityKind;
  name: string;
  papers: number;
  /** Citations of those papers, summed; papers without a known count add nothing. */
  citations: number;
  /** Its most cited paper (the first one when no count is known). */
  top: Paper;
  topCitations: number | undefined;
  /** For an author, how many people the name seems to be, when more than one. */
  people?: number;
}

/**
 * Institutions or authors of `papers`, most papers (or citations) first.
 *
 * Names are merged and spelled exactly as in the graph, which builds them: the same
 * institution, whatever the affiliation string, and never an author listed as one. How many
 * people an author's name seems to be is told of the first `shown` rows only.
 */
export function rankEntities(
  papers: readonly Paper[],
  kind: EntityKind,
  metric: RankingMetric,
  citations: ReadonlyMap<string, number>,
  shown = Number.POSITIVE_INFINITY,
): RankedEntity[] {
  // The graph's nodes alone, which it names, without its papers' nodes nor links: the
  // authors of every stored paper took 254 MB and a second to link (WEB-6).
  const graph = buildGraph([...papers], {
    papers: false,
    links: false,
    people: false,
    institutions: kind === "institution",
    authors: kind === "author",
    minPapers: { institution: 1, author: 1 },
    isolated: true,
    maxNodes: Number.POSITIVE_INFINITY,
    citations,
  });
  const byId = new Map(papers.map((paper) => [paper.arxiv_id, paper]));
  const ranked: RankedEntity[] = [];
  for (const node of graph.nodes) {
    if (!isEntity(node) || node.kind !== kind) continue;
    const topId = node.paperIds.reduce((best, id) =>
      (citations.get(id) ?? -1) > (citations.get(best) ?? -1) ? id : best,
    );
    const top = byId.get(topId);
    if (!top) continue;
    ranked.push({
      id: node.id,
      kind,
      name: node.label,
      papers: node.paperIds.length,
      citations: node.citations,
      top,
      topCitations: citations.get(topId),
    });
  }
  const [first, second] =
    metric === "papers" ? (["papers", "citations"] as const) : (["citations", "papers"] as const);
  ranked.sort(
    (a, b) => b[first] - a[first] || b[second] - a[second] || a.name.localeCompare(b.name),
  );
  if (kind === "author") {
    const rows = ranked.slice(0, shown);
    const people = authorPeople(papers, new Set(rows.map(({ id }) => id)));
    for (const row of rows) {
      const count = people.get(row.id);
      if (count !== undefined) row.people = count;
    }
  }
  return ranked;
}
