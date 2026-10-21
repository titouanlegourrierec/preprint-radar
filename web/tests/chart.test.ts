import { describe, expect, it } from "vitest";
import { areaPath, linePath, niceTicks, xScale } from "../src/chart";

describe("niceTicks", () => {
  it("names round values from 0 to the largest or just past it", () => {
    expect(niceTicks(0.023)).toEqual([0, 0.01, 0.02, 0.03]);
    expect(niceTicks(100)).toEqual([0, 25, 50, 75, 100]);
    expect(niceTicks(7, 3)).toEqual([0, 2.5, 5, 7.5]);
    expect(niceTicks(0.0036)).toEqual([0, 0.001, 0.002, 0.003, 0.004]);
    expect(niceTicks(0)).toEqual([0]);
  });
});

describe("xScale", () => {
  it("spreads the points over the plot and finds the nearest", () => {
    const scale = xScale(5, 40, 400);
    expect([0, 1, 4].map(scale.at)).toEqual([40, 140, 440]);
    expect(scale.nearest(180)).toBe(1);
    expect(scale.nearest(200)).toBe(2);
    expect(scale.nearest(-50)).toBe(0);
    expect(scale.nearest(900)).toBe(4);
  });

  it("centers a single point", () => {
    const scale = xScale(1, 40, 400);
    expect(scale.at(0)).toBe(240);
    expect(scale.nearest(10)).toBe(0);
  });
});

describe("paths", () => {
  const x = (index: number) => index * 10;
  const y = (value: number) => 100 - value;

  it("draw a line broken where a value is missing", () => {
    expect(linePath([1, 2, null, 4, 5], x, y)).toBe("M0 99L10 98M30 96L40 95");
    expect(linePath([null], x, y)).toBe("");
  });

  it("close each run of the area on the baseline", () => {
    expect(areaPath([1, 2, null, 4], x, y, 100)).toBe(
      "M0 99L10 98L10 100L0 100ZM30 96L30 100L30 100Z",
    );
    expect(areaPath([], x, y, 100)).toBe("");
  });
});
