import { describe, expect, it } from "vitest";
import { citationRadius, fitTransform, nodeRadius } from "../src/graph-renderer";

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
