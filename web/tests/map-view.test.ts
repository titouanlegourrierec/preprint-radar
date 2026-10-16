import type { Feature, Geometry } from "geojson";
import { describe, expect, it } from "vitest";
import {
  anchorOf,
  centerOn,
  clampZoom,
  easeInOut,
  facing,
  MAX_ZOOM,
  panBy,
  rotateBy,
  turnTowards,
  UNZOOMED,
  wheelFactor,
  zoomAbout,
  zoomed,
} from "../src/map-view";

const WIDTH = 960;
const HEIGHT = 480;

describe("the flat map's zoom (UX-43)", () => {
  it("keeps the point zoomed about where it is", () => {
    const zoom = zoomAbout(UNZOOMED, 2, [300, 200], WIDTH, HEIGHT);
    expect(zoom).toEqual({ k: 2, x: -300, y: -200 });
    expect(zoomed(zoom, [300, 200])).toEqual([300, 200]);
  });

  it("stays between the whole map and eight times it", () => {
    expect(zoomAbout(UNZOOMED, 0.5, [300, 200], WIDTH, HEIGHT)).toEqual(UNZOOMED);
    expect(zoomAbout(UNZOOMED, 100, [0, 0], WIDTH, HEIGHT).k).toBe(MAX_ZOOM);
  });

  it("never moves the map past the frame's edges", () => {
    const zoom = { k: 2, x: -300, y: -200 };
    expect(panBy(zoom, 1000, 1000, WIDTH, HEIGHT)).toEqual({ k: 2, x: 0, y: 0 });
    expect(panBy(zoom, -1000, -1000, WIDTH, HEIGHT)).toEqual({ k: 2, x: -WIDTH, y: -HEIGHT });
    expect(panBy(UNZOOMED, 50, 50, WIDTH, HEIGHT)).toEqual(UNZOOMED);
    expect(clampZoom({ k: 0.2, x: 10, y: 10 }, WIDTH, HEIGHT)).toEqual(UNZOOMED);
  });

  it("brings a point to the center, as near as the edges allow", () => {
    expect(centerOn({ k: 4, x: 0, y: 0 }, [480, 240], WIDTH, HEIGHT)).toEqual({
      k: 4,
      x: -1440,
      y: -720,
    });
    expect(centerOn({ k: 4, x: -1000, y: -500 }, [10, 10], WIDTH, HEIGHT)).toEqual({
      k: 4,
      x: 0,
      y: 0,
    });
  });

  it("zooms in as the wheel turns up, faster for a pinch, twice at most", () => {
    expect(wheelFactor(-100, 0, false)).toBeCloseTo(2 ** 0.2);
    expect(wheelFactor(100, 0, false)).toBeLessThan(1);
    expect(wheelFactor(-3, 1, false)).toBeCloseTo(wheelFactor(-75, 0, false));
    expect(wheelFactor(-10, 0, true)).toBeCloseTo(2 ** 0.2);
    expect(wheelFactor(1, 2, false)).toBe(0.5);
    expect(wheelFactor(-100, 0, true)).toBe(2);
  });
});

describe("the globe's rotation (UX-43)", () => {
  it("faces a point, and follows the pointer near the center", () => {
    expect(facing([116, 40])).toEqual([-116, -40]);
    // A drag of the radius turns it by a radian.
    const [longitude, latitude] = rotateBy([0, 0], 100, -100, 100);
    expect(longitude).toBeCloseTo(180 / Math.PI);
    expect(latitude).toBeCloseTo(180 / Math.PI);
    expect(rotateBy([0, 80], 0, -1000, 100)).toEqual([0, 90]);
  });

  it("turns the short way round", () => {
    expect(turnTowards([170, 0], [-170, 20], 0.5)).toEqual([180, 10]);
    expect(turnTowards([-170, 0], [170, 0], 1)).toEqual([-190, 0]);
    expect(turnTowards([10, 0], [50, 0], 0.25)).toEqual([20, 0]);
  });

  it("eases in and out", () => {
    expect([easeInOut(0), easeInOut(0.5), easeInOut(1)]).toEqual([0, 0.5, 1]);
    expect(easeInOut(0.1)).toBeLessThan(0.1);
    expect(easeInOut(0.9)).toBeGreaterThan(0.9);
  });
});

describe("anchorOf", () => {
  const square = (x: number, y: number, size: number) => [
    [
      [x, y],
      [x, y + size],
      [x + size, y + size],
      [x + size, y],
      [x, y],
    ],
  ];

  it("points at a country's largest part", () => {
    const country: Feature<Geometry> = {
      type: "Feature",
      properties: {},
      geometry: { type: "MultiPolygon", coordinates: [square(-60, 0, 2), square(0, 40, 6)] },
    };
    const [longitude, latitude] = anchorOf(country);
    expect(longitude).toBeCloseTo(3, 0);
    expect(latitude).toBeCloseTo(43, 0);
  });

  it("points at the center of a country in one piece", () => {
    const country: Feature<Geometry> = {
      type: "Feature",
      properties: {},
      geometry: { type: "Polygon", coordinates: square(10, 10, 2) },
    };
    const [longitude, latitude] = anchorOf(country);
    expect(longitude).toBeCloseTo(11, 1);
    expect(latitude).toBeCloseTo(11, 1);
  });
});
