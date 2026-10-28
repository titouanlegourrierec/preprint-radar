import { describe, expect, it } from "vitest";
import {
  citationRadius,
  fitTransform,
  largestRadius,
  logoBox,
  nodeRadius,
  peekLinks,
  pinchView,
  sizeScale,
  zoomAbout,
} from "../src/graph-renderer";

describe("fitTransform", () => {
  const bounds = { minX: -100, minY: -50, maxX: 100, maxY: 50 };

  it("centers the bounds in the canvas", () => {
    const view = fitTransform(bounds, 496, 296);

    expect(view.k).toBeCloseTo(2);
    expect(view.x).toBeCloseTo(248);
    expect(view.y).toBeCloseTo(148);
  });

  it("keeps the graph out from under overlays", () => {
    const view = fitTransform(bounds, 896, 1000, { left: 300, right: 200 });

    // 396 px are free between the overlays: centered at 300 + 198.
    expect(view.k).toBeCloseTo(1.5);
    expect(view.x).toBeCloseTo(498);
  });

  it("never zooms in further than 2x", () => {
    expect(fitTransform({ minX: 0, minY: 0, maxX: 1, maxY: 1 }, 800, 600).k).toBe(2);
  });
});

describe("nodeRadius", () => {
  it("keeps single-paper nodes small and grows in proportion to the papers past the first", () => {
    expect(nodeRadius(1, 177)).toBe(2.5);
    // A month of cs.CV: Tsinghua's 177 papers get the largest size, 89 half of the growth.
    expect(nodeRadius(177, 177)).toBeCloseTo(64);
    expect(nodeRadius(89, 177)).toBeCloseTo(2.5 + 61.5 / 2);
  });

  it("sizes a graph of few papers as if its biggest node had 21, and is capped", () => {
    expect(nodeRadius(11, 5)).toBeCloseTo(2.5 + 61.5 / 2);
    expect(nodeRadius(11, 5)).toBe(nodeRadius(11));
    expect(nodeRadius(1000)).toBe(64);
  });
});

describe("citationRadius", () => {
  const growth = (radius: number) => (radius - 2.5) / 61.5;

  it("grows in proportion to citations, as Rankings' bars, out of the graph's most cited", () => {
    // All time: Google's 892,816 citations and Carnegie Mellon's 206,031.
    expect(citationRadius(892_816, 892_816)).toBeCloseTo(64);
    expect(growth(citationRadius(206_031, 892_816))).toBeCloseTo(206_031 / 892_816);
    expect(citationRadius(0, 892_816)).toBe(2.5);
  });

  it("never makes a hub of a few citations in a graph of few, and is capped", () => {
    expect(citationRadius(3, 3)).toBeLessThan(5);
    expect(citationRadius(250_000)).toBe(64);
  });
});

describe("the contrast of sizes", () => {
  const growth = (radius: number) => (radius - 2.5) / 61.5;

  it("draws areas in proportion halfway to the left", () => {
    expect(growth(citationRadius(206_031, 892_816, -0.5)) ** 2).toBeCloseTo(206_031 / 892_816);
  });

  it("draws sizes together further left, as a logarithm would, and apart to the right", () => {
    const sizes = (contrast: number) =>
      [1, 5, 30].map((citations) => citationRadius(citations, 162, contrast));
    const [soft, even, strong] = [sizes(-1), sizes(0), sizes(1)];
    const ratio = (radii: number[]) => (radii[2] ?? 0) / (radii[0] ?? 1);
    // Softer: 30 citations closer to 1, which stands well out of the smallest size.
    expect(ratio(soft)).toBeLessThan(ratio(even));
    expect((soft[0] ?? 0) - 2.5).toBeGreaterThan(5);
    expect(strong[2]).toBeLessThan(even[2] ?? 0);
    expect(citationRadius(162, 162, 1)).toBeCloseTo(64);
    expect(nodeRadius(60, 177, 1)).toBeLessThan(nodeRadius(60, 177));
  });
});

describe("largestRadius", () => {
  it("grows with the square root of a large graph's node count, as its extent does", () => {
    expect(largestRadius(1_850)).toBe(64);
    expect(largestRadius(8_000)).toBeCloseTo(128);
  });
});

describe("sizeScale", () => {
  it("is the most papers and the most citations of the graph's nodes", () => {
    const node = (paperIds: string[], citations: number) =>
      ({
        id: paperIds.join(),
        kind: "institution",
        label: "",
        key: "",
        paperIds,
        citations,
      }) as const;
    expect(
      sizeScale({ nodes: [node(["a", "b", "c"], 4), node(["d"], 90)], links: [] } as never),
    ).toEqual({ papers: 3, citations: 90, nodes: 2 });
  });
});

describe("zoomAbout", () => {
  it("keeps the point under the cursor where it is", () => {
    const view = { x: 10, y: 20, k: 1 };
    const zoomed = zoomAbout(view, 110, 220, 2);

    expect(zoomed.k).toBe(2);
    // The graph point under (110, 220) was (100, 200); it still is.
    expect((110 - zoomed.x) / zoomed.k).toBe(100);
    expect((220 - zoomed.y) / zoomed.k).toBe(200);
  });

  it("stays within the zoom limits", () => {
    expect(zoomAbout({ x: 0, y: 0, k: 7 }, 0, 0, 10).k).toBe(8);
    expect(zoomAbout({ x: 0, y: 0, k: 0.03 }, 0, 0, 0.1).k).toBe(0.02);
  });
});

describe("pinchView", () => {
  const start = { x: 0, y: 0, k: 1 };

  it("zooms by the ratio of the fingers' distances", () => {
    const view = pinchView(
      start,
      [
        { x: 90, y: 100 },
        { x: 110, y: 100 },
      ],
      [
        { x: 80, y: 100 },
        { x: 120, y: 100 },
      ],
    );

    expect(view).toEqual({ k: 2, x: -100, y: -100 });
  });

  it("pans with the fingers' midpoint", () => {
    const view = pinchView(
      start,
      [
        { x: 0, y: 0 },
        { x: 10, y: 0 },
      ],
      [
        { x: 30, y: 40 },
        { x: 40, y: 40 },
      ],
    );

    expect(view).toEqual({ k: 1, x: 30, y: 40 });
  });
});

describe("peekLinks", () => {
  const link = (a: string, b: string) => ({ source: { id: a }, target: { id: b } });
  const links = [
    link("A", "p1"),
    link("B", "p1"),
    link("A", "p2"),
    link("B", "p2"),
    link("A", "p3"),
    link("A", "B"),
  ];
  const linksOf = new Map<string, ReturnType<typeof link>[]>();
  for (const each of links) {
    for (const end of [each.source.id, each.target.id])
      linksOf.set(end, [...(linksOf.get(end) ?? []), each]);
  }

  it("gives two nodes' own link and their paths through the nodes both link to (UX-61)", () => {
    const path = peekLinks("A", "B", linksOf);
    expect(new Set(path)).toEqual(new Set([links[0], links[1], links[2], links[3], links[5]]));
    // A paper of one alone is not on the way.
    expect(path).not.toContain(links[4]);
    expect(peekLinks("A", "unknown", linksOf)).toEqual([]);
  });
});

describe("logoBox (PROD-23)", () => {
  const corner = ({ x, y, w, h }: { x: number; y: number; w: number; h: number }) =>
    Math.hypot(x + w - 5, y + h - 7);

  it("centers a logo of its own proportions on the node", () => {
    const square = logoBox(5, 7, 10, 24, 24);
    expect(square.w).toBeCloseTo(square.h);
    expect(square.x + square.w / 2).toBeCloseTo(5);
    expect(square.y + square.h / 2).toBeCloseTo(7);
    const wide = logoBox(5, 7, 10, 318, 100);
    expect(wide.w / wide.h).toBeCloseTo(3.18);
  });

  it("gives a wide mark the disc's width, its corners just inside the disc", () => {
    const square = logoBox(5, 7, 10, 1, 1);
    const wide = logoBox(5, 7, 10, 318, 100);
    expect(corner(square)).toBeCloseTo(corner(wide));
    expect(corner(wide)).toBeLessThan(10);
    expect(corner(wide)).toBeGreaterThan(8.5);
    expect(wide.w).toBeGreaterThan(square.w);
  });
});
