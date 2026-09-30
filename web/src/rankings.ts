import { buildGraph, type EntityKind, isEntity } from "./graph";
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
}

/**
 * Institutions or authors of `papers`, most papers (or citations) first.
 *
 * Names are merged and spelled exactly as in the graph, which builds them: the same
 * institution, whatever the affiliation string, and never an author listed as one.
 */
export function rankEntities(
  papers: readonly Paper[],
  kind: EntityKind,
  metric: RankingMetric,
  citations: ReadonlyMap<string, number>,
): RankedEntity[] {
  const graph = buildGraph([...papers], {
    // Papers on: each entity is then linked to its papers only, not to every co-author.
    papers: true,
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
  return ranked.sort(
    (a, b) => b[first] - a[first] || b[second] - a[second] || a.name.localeCompare(b.name),
  );
}
