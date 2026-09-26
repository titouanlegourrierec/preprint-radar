import { describe, expect, it } from "vitest";
import { initialPositions, inLargestComponent, type Point } from "../src/graph-layout";

const distance = (a: Point | undefined, b: Point | undefined) =>
  a && b ? Math.hypot(a.x - b.x, a.y - b.y) : Number.NaN;

// A triangle (0, 1, 2), a pair (3, 4) and an isolated node (5).
const links = [
  [0, 1],
  [1, 2],
  [2, 0],
  [3, 4],
] as const;

describe("initialPositions", () => {
  it("keeps known positions and starts new neighbors next to them", () => {
    const known = [{ x: 500, y: -200 }, undefined, undefined, undefined, undefined, undefined];
    const positions = initialPositions(6, links, known);

    expect(positions[0]).toEqual({ x: 500, y: -200 });
    expect(distance(positions[1], positions[0])).toBeLessThan(30);
    expect(distance(positions[2], positions[0])).toBeLessThan(30);
  });

  it("starts each component in one piece, the biggest in the center", () => {
    const positions = initialPositions(6, links, []);

    expect(distance(positions[0], { x: 0, y: 0 })).toBeLessThan(40);
    expect(distance(positions[3], positions[4])).toBeLessThan(40);
    expect(distance(positions[0], positions[3])).toBeGreaterThan(
      distance(positions[3], positions[4]),
    );
  });

  it("puts new components around what is already placed", () => {
    const known = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 50, y: 80 },
    ];
    const positions = initialPositions(6, links, known);

    for (const index of [3, 4, 5]) {
      expect(distance(positions[index], { x: 50, y: 27 })).toBeGreaterThan(50);
    }
  });
});

describe("inLargestComponent", () => {
  it("marks the nodes of the largest connected component", () => {
    expect(inLargestComponent(6, links)).toEqual([true, true, true, false, false, false]);
  });
});
