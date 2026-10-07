import { describe, expect, it } from "vitest";
import type { Graph } from "../src/graph";
import { exportName, GRAPH_SOURCES, toGraphML } from "../src/graph-export";

describe("toGraphML", () => {
  const graph: Graph = {
    nodes: [
      {
        id: "institution:mit",
        kind: "institution",
        label: "MIT",
        key: "mit",
        paperIds: ["1", "2"],
        citations: 12,
        rorId: "042nb2s44",
      },
      {
        id: "author:ada & bob",
        kind: "author",
        label: 'Ada "&" <Bob>',
        key: "ada bob",
        paperIds: ["1"],
        citations: 3,
      },
    ],
    links: [{ source: "institution:mit", target: "author:ada & bob", weight: 1 }],
    truncated: false,
    consortia: 0,
  };

  it("declares the attributes and writes the nodes and links, escaped", () => {
    const text = toGraphML(graph);
    expect(text).toContain('<key id="weight" for="edge" attr.name="weight" attr.type="int"/>');
    expect(text).toContain(
      '<node id="institution:mit"><data key="label">MIT</data><data key="kind">institution</data><data key="papers">2</data><data key="citations">12</data><data key="ror">042nb2s44</data></node>',
    );
    expect(text).toContain('<data key="label">Ada &quot;&amp;&quot; &lt;Bob&gt;</data>');
    expect(text).not.toContain(
      '<node id="author:ada &amp; bob"><data key="label">Ada &quot;&amp;&quot; &lt;Bob&gt;</data><data key="kind">author</data><data key="papers">1</data><data key="citations">3</data><data key="ror">',
    );
    expect(text).toContain(
      '<edge source="institution:mit" target="author:ada &amp; bob"><data key="weight">1</data></edge>',
    );
    expect(text.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true);
    // Where the data comes from, and what the export shows when told.
    expect(text).toContain(`<desc>${GRAPH_SOURCES.replaceAll("&", "&amp;")}</desc>`);
    expect(toGraphML(graph, "Last 5 days & more")).toContain("<desc>Last 5 days &amp; more</desc>");
  });

  it("names the files by day, and by the node focused on", () => {
    expect(exportName("2026-10-07", null)).toBe("preprint-radar-graph-2026-10-07");
    expect(exportName("2026-10-07", "institution:massachusetts institute of technology")).toBe(
      "preprint-radar-graph-institution-massachusetts-institute-of-technology-2026-10-07",
    );
    expect(exportName("2026-10-07", "author:Jürgen Müller")).toBe(
      "preprint-radar-graph-author-jurgen-muller-2026-10-07",
    );
    expect(exportName("2026-10-07", "author:王小明")).toBe(
      "preprint-radar-graph-author-王小明-2026-10-07",
    );
  });
});
