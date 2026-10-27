import { describe, expect, it } from "vitest";
import {
  citationRadius,
  fitTransform,
  nodeRadius,
  peekLinks,
  pinchView,
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
  it("keeps single-paper nodes small and grows with the paper count", () => {
    expect(nodeRadius(1)).toBe(2.5);
    expect(nodeRadius(2)).toBe(6);
    expect(nodeRadius(5)).toBe(9.5);
    expect(nodeRadius(10)).toBe(13);
  });

  it("is capped for very prolific nodes", () => {
    expect(nodeRadius(1000)).toBe(28);
  });
});

describe("citationRadius", () => {
  it("tells apart the small counts of recent papers", () => {
    expect(citationRadius(0)).toBe(2.5);
    expect(citationRadius(1)).toBe(5.5);
    expect(citationRadius(3)).toBe(8.5);
    expect(citationRadius(31)).toBe(17.5);
  });

  it("is capped for highly cited nodes", () => {
    expect(citationRadius(250_000)).toBe(28);
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
