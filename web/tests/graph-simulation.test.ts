import { describe, expect, it } from "vitest";
import {
  coolingDecay,
  type ForceSettings,
  LARGE_GRAPH,
  Layout,
  type LayoutGraph,
} from "../src/graph-simulation";

const SETTINGS: ForceSettings = {
  centerForce: 0.3,
  repelForce: 12,
  linkForce: 1,
  linkDistance: 40,
};

/** A chain of `count` nodes on a line, linked one to the next, with a lone node at the end. */
function chain(count: number): LayoutGraph {
  const positions = new Float32Array(2 * (count + 1));
  for (let index = 0; index <= count; index++) positions[2 * index] = 10 * index;
  const links = new Uint32Array(2 * (count - 1));
  for (let index = 0; index + 1 < count; index++) {
    links[2 * index] = index;
    links[2 * index + 1] = index + 1;
  }
  return {
    positions,
    radii: new Float32Array(count + 1).fill(4),
    degrees: Uint32Array.from({ length: count + 1 }, (_, index) =>
      index === count ? 0 : index === 0 || index === count - 1 ? 1 : 2,
    ),
    main: Uint8Array.from({ length: count + 1 }, (_, index) => (index === count ? 0 : 1)),
    links,
    weights: new Float32Array(count - 1).fill(1),
  };
}

function point(layout: Layout, index: number): { x: number; y: number } {
  const positions = layout.positions();
  return { x: positions[2 * index] ?? Number.NaN, y: positions[2 * index + 1] ?? Number.NaN };
}

function runToRest(layout: Layout): number {
  let steps = 0;
  while (layout.step()) steps++;
  return steps;
}

/** Ticks a decay takes from alpha 1 to d3's default rest (alphaMin 0.001). */
function ticksOf(decay: number): number {
  return Math.log(0.001) / Math.log(1 - decay);
}

describe("coolingDecay", () => {
  it("cools a graph of up to 2,500 nodes in 530 ticks, larger ones in fewer, down to 80", () => {
    expect(ticksOf(coolingDecay(6))).toBeCloseTo(530);
    expect(ticksOf(coolingDecay(2500))).toBeCloseTo(530);
    expect(ticksOf(coolingDecay(10_000))).toBeCloseTo(132.5);
    expect(ticksOf(coolingDecay(100_000))).toBeCloseTo(80);
  });
});

describe("Layout", () => {
  it("moves from the starting positions to rest, one step at a time", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 1);

    expect(layout.running).toBe(true);
    // The cooling, then the short last pass with collisions (UX-30).
    expect(runToRest(layout)).toBeGreaterThan(ticksOf(coolingDecay(6)) + 50);
    expect(layout.running).toBe(false);
    expect(layout.step()).toBe(false);
    const positions = layout.positions();
    expect(positions).toHaveLength(12);
    expect([...positions].every(Number.isFinite)).toBe(true);
    // Linked nodes end up about a link apart, closer than the chain's two ends.
    const [a, b, end] = [point(layout, 0), point(layout, 1), point(layout, 4)];
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeLessThan(Math.hypot(a.x - end.x, a.y - end.y));
  });

  it("hides the start of a cooling, where the starting positions burst open", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 1);
    expect(layout.hidden).toBe(true);
    let ticks = 0;
    while (layout.hidden) {
      layout.step();
      ticks++;
    }
    // Hidden down to alpha 0.3: about a fifth of the cooling.
    expect(ticks).toBeCloseTo(Math.log(0.3) / Math.log(1 - coolingDecay(6)), -1);
    expect(layout.running).toBe(true);

    // A graph laid out already, or Reheat, settles in sight.
    layout.setGraph(chain(5), 0.4);
    expect(layout.hidden).toBe(false);
    runToRest(layout);
    layout.heat(1);
    expect(layout.hidden).toBe(false);
  });

  it("starts a graph already laid out at a lower alpha, and settles at once if asked", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 0.4);
    const fromWarm = runToRest(layout);

    layout.setGraph(chain(5), 1);
    expect(runToRest(layout)).toBeGreaterThan(fromWarm);

    layout.setGraph(chain(5), 1);
    layout.settle();
    expect(layout.running).toBe(false);
  });

  it("settles a large graph without the last pass, which has no collisions to part", () => {
    // Nearly cold, so that a graph of 2,000 nodes takes a few dozen ticks: settling back
    // alone (d3's decay), where a small graph adds the last pass's (from alpha 0.1).
    const settleTicks = Math.ceil(Math.log(0.001 / 0.002) / Math.log(1 - 0.0228));
    const small = new Layout(SETTINGS);
    small.setGraph(chain(5), 0.002);
    expect(runToRest(small)).toBeGreaterThan(settleTicks + 50);

    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(LARGE_GRAPH + 1), 0.002);
    expect(runToRest(layout)).toBeLessThanOrEqual(settleTicks);

    layout.setGraph(chain(LARGE_GRAPH + 1), 0.002);
    layout.settle();
    expect(layout.running).toBe(false);
    expect([...layout.positions()].every(Number.isFinite)).toBe(true);
  });

  it("settles back gently from Reheat, and never cools down a layout warmer than asked", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 1);
    const cold = runToRest(layout);

    // d3's decay from 0.5 is shorter than the first cooling from 1.
    layout.heat(0.5);
    expect(layout.running).toBe(true);
    expect(runToRest(layout)).toBeLessThan(cold);

    layout.setGraph(chain(5), 1);
    layout.heat(0.3);
    expect(runToRest(layout)).toBe(cold);
  });

  it("holds a dragged node at the pointer and cools down once released", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 1);
    runToRest(layout);

    layout.pin(2, 500, -300, true);
    expect(layout.running).toBe(true);
    for (let tick = 0; tick < 50; tick++) layout.step();
    expect(point(layout, 2)).toEqual({ x: 500, y: -300 });
    // Its neighbors follow it.
    expect(point(layout, 1).x).toBeGreaterThan(100);

    layout.release(2);
    // At rest, a drag settles as the last pass does: quickly.
    expect(runToRest(layout)).toBeLessThan(ticksOf(coolingDecay(6)));
    expect(layout.running).toBe(false);
  });

  it("goes on cooling when a node is dragged before the layout is at rest", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 1);
    for (let tick = 0; tick < 10; tick++) layout.step();

    layout.pin(2, 500, -300, true);
    layout.step();
    layout.release(2);
    expect(runToRest(layout)).toBeGreaterThan(ticksOf(coolingDecay(6)) / 2);
  });

  it("moves a node at once without moving the others under reduced motion", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 1);
    layout.settle();
    const neighbor = point(layout, 1);

    layout.pin(2, 500, -300, false);

    expect(point(layout, 2)).toEqual({ x: 500, y: -300 });
    expect(point(layout, 1)).toEqual(neighbor);
    expect(layout.running).toBe(false);
  });

  it("heats up again after new forces, and takes new radii", () => {
    const layout = new Layout(SETTINGS);
    layout.setGraph(chain(5), 1);
    runToRest(layout);
    const before = point(layout, 0);

    layout.setForces({ ...SETTINGS, linkDistance: 200 }, new Float32Array(6).fill(10));
    layout.heat(0.3);
    expect(layout.running).toBe(true);
    runToRest(layout);
    const after = point(layout, 0);
    expect(after).not.toEqual(before);
  });

  it("ignores links to missing nodes, and pins of missing nodes", () => {
    const graph = chain(3);
    const layout = new Layout(SETTINGS);
    layout.setGraph({ ...graph, links: Uint32Array.from([0, 1, 1, 99]) }, 1);
    layout.pin(99, 0, 0, true);
    layout.release(99);

    runToRest(layout);
    expect(layout.positions()).toHaveLength(8);
  });
});
