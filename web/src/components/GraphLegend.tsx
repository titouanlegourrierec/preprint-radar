import { countOf } from "../format";
import { type Graph, MAX_CLIQUE_AUTHORS, type NodeKind } from "../graph";

const KINDS = [
  ["paper", "Papers"],
  ["institution", "Institutions"],
  ["author", "Authors"],
] as const;

/**
 * What the graph draws: its nodes of each kind, its links, the institutions and authors the
 * cap leaves out, the consortia left unlinked.
 */
export function GraphLegend({
  graph,
  counts,
  cap,
}: {
  graph: Graph;
  counts: Record<NodeKind, number>;
  /** The settings' "Top institutions & authors", when it cut some (UX-20). */
  cap: number;
}) {
  return (
    <div class="graph__legend">
      {KINDS.map(
        ([kind, name]) =>
          counts[kind] > 0 && (
            <span key={kind}>
              <i class={`graph__dot graph__dot--${kind}`} />
              {name} ({counts[kind].toLocaleString()})
            </span>
          ),
      )}
      <span>{countOf(graph.links.length, "link")}</span>
      {graph.truncated && (
        <span>
          top {cap.toLocaleString()} of{" "}
          {countOf(graph.eligible, "institution and author", "institutions and authors")}
        </span>
      )}
      {graph.consortia > 0 && (
        <span>
          {countOf(graph.consortia, "paper")} of over {MAX_CLIQUE_AUTHORS} authors, whose authors
          are not linked to one another
        </span>
      )}
    </div>
  );
}
