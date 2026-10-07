import { feedSlug } from "./feeds";
import type { Graph } from "./graph";
import { xmlText } from "./xml";

// The attributes of nodes and links, as GraphML declares them: Gephi, Cytoscape and
// NetworkX read them by these names.
const KEYS = [
  ["label", "node", "string"],
  ["kind", "node", "string"],
  ["papers", "node", "int"],
  ["citations", "node", "int"],
  ["ror", "node", "string"],
  ["weight", "edge", "int"],
] as const;

/** Where the graph's data comes from, which the GraphML export says (REL-10). */
export const GRAPH_SOURCES =
  "Papers from arXiv; institutions from the Research Organization Registry and OpenAlex; " +
  "citation counts from Semantic Scholar. Made with Preprint Radar.";

/**
 * The graph shown as GraphML (§17.1 #8), for Gephi, Cytoscape or NetworkX: its nodes with
 * their kind, name, papers and citations (and an institution's ROR id), its links with the
 * number of papers they stand for (`weight`), and where its data comes from (`about`,
 * REL-10).
 */
export function toGraphML(graph: Graph, about = GRAPH_SOURCES): string {
  const data = (key: string, value: string | number) =>
    `<data key="${key}">${xmlText(String(value))}</data>`;
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
    `  <desc>${xmlText(about)}</desc>`,
    ...KEYS.map(
      ([name, kind, type]) =>
        `  <key id="${name}" for="${kind}" attr.name="${name}" attr.type="${type}"/>`,
    ),
    '  <graph edgedefault="undirected">',
    ...graph.nodes.map(
      (node) =>
        `    <node id="${xmlText(node.id)}">` +
        data("label", node.label) +
        data("kind", node.kind) +
        data("papers", node.paperIds.length) +
        data("citations", node.citations) +
        (node.rorId ? data("ror", node.rorId) : "") +
        "</node>",
    ),
    ...graph.links.map(
      (link) =>
        `    <edge source="${xmlText(link.source)}" target="${xmlText(link.target)}">` +
        data("weight", link.weight) +
        "</edge>",
    ),
    "  </graph>",
    "</graphml>",
    "",
  ].join("\n");
}

/** A file name for the graph's exports: "preprint-radar-graph-2026-10-07". */
export function exportName(day: string, focus: string | null): string {
  if (focus === null) return `preprint-radar-graph-${day}`;
  // "author:Jürgen Müller" is "author-jurgen-muller"; a name in any script keeps its letters.
  const separator = focus.indexOf(":");
  const name = feedSlug(focus.slice(separator + 1));
  const kind = focus.slice(0, separator);
  return `preprint-radar-graph-${[kind, name].filter(Boolean).join("-")}-${day}`;
}
