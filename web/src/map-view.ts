/**
 * How Rankings' world map is looked at (UX-43): the flat map zoomed and moved, the globe
 * turned and zoomed. Pure geometry, in the units of the map's viewBox; the component turns
 * pointer and wheel events into these.
 */
import { geoArea, geoCentroid } from "d3-geo";
import type { Feature, Geometry, Polygon } from "geojson";

/** How far in either view zooms: eight times, a country of Europe the frame's width. */
export const MAX_ZOOM = 8;

/** The flat map's zoom: its scale, then its translation. */
export interface Zoom {
  k: number;
  x: number;
  y: number;
}

export const UNZOOMED: Zoom = { k: 1, x: 0, y: 0 };

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

/** The zoom kept to the map: never smaller than the frame, nor moved past its edges. */
export function clampZoom(zoom: Zoom, width: number, height: number): Zoom {
  const k = clamp(zoom.k, 1, MAX_ZOOM);
  return { k, x: clamp(zoom.x, width * (1 - k), 0), y: clamp(zoom.y, height * (1 - k), 0) };
}

/** Zoomed by `factor` about a point of the frame, which stays where it is. */
export function zoomAbout(
  zoom: Zoom,
  factor: number,
  [px, py]: readonly [number, number],
  width: number,
  height: number,
): Zoom {
  const k = clamp(zoom.k * factor, 1, MAX_ZOOM);
  const ratio = k / zoom.k;
  return clampZoom(
    { k, x: px - (px - zoom.x) * ratio, y: py - (py - zoom.y) * ratio },
    width,
    height,
  );
}

/** Moved by a drag of `dx`, `dy`. */
export function panBy(zoom: Zoom, dx: number, dy: number, width: number, height: number): Zoom {
  return clampZoom({ ...zoom, x: zoom.x + dx, y: zoom.y + dy }, width, height);
}

/** Moved so that a point of the map is at the frame's center, as near as its edges allow. */
export function centerOn(
  zoom: Zoom,
  [x, y]: readonly [number, number],
  width: number,
  height: number,
): Zoom {
  return clampZoom(
    { k: zoom.k, x: width / 2 - x * zoom.k, y: height / 2 - y * zoom.k },
    width,
    height,
  );
}

/** Where a point of the map is in the frame. */
export function zoomed(zoom: Zoom, [x, y]: readonly [number, number]): [number, number] {
  return [x * zoom.k + zoom.x, y * zoom.k + zoom.y];
}

/**
 * The zoom of a wheel's turn, or of a trackpad's pinch, which comes as a wheel with Ctrl
 * and smaller steps (`pinch`): d3-zoom's, a notch of a mouse wheel zooming by a seventh,
 * and never more than twice at once.
 */
export function wheelFactor(deltaY: number, deltaMode: number, pinch: boolean): number {
  // Lines (Firefox's mouse wheel) are about 25 pixels, pages too many.
  const pixels = deltaY * (deltaMode === 1 ? 25 : deltaMode === 2 ? 500 : 1);
  return clamp(2 ** (-pixels * 0.002 * (pinch ? 10 : 1)), 0.5, 2);
}

/** The globe's rotation, d3's `[λ, φ]`: the point facing the viewer is `[-λ, -φ]`. */
export type Rotation = readonly [number, number];

/** The rotation that faces a point `[longitude, latitude]`. */
export function facing([longitude, latitude]: readonly [number, number]): Rotation {
  return [-longitude, -latitude];
}

/**
 * Turned by a drag of `dx`, `dy` on a globe of this radius: the point under the pointer
 * follows it, near the center; the poles stop it.
 */
export function rotateBy(rotation: Rotation, dx: number, dy: number, radius: number): Rotation {
  const degrees = 180 / Math.PI / radius;
  return [rotation[0] + dx * degrees, clamp(rotation[1] - dy * degrees, -90, 90)];
}

/** A rotation a fraction `t` of the way to another, the short way round. */
export function turnTowards(from: Rotation, to: Rotation, t: number): Rotation {
  const longitude = ((((to[0] - from[0]) % 360) + 540) % 360) - 180;
  return [from[0] + longitude * t, from[1] + (to[1] - from[1]) * t];
}

/** Slow at both ends: a turn of the globe. */
export function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2;
}

/**
 * Where a country's tooltip points, `[longitude, latitude]`: the center of its largest part,
 * the mainland of a country with islands or overseas lands (France's is not in the Atlantic).
 */
export function anchorOf(country: Feature<Geometry | null>): [number, number] {
  const { geometry } = country;
  if (geometry?.type !== "MultiPolygon") return geoCentroid(country);
  const parts: Polygon[] = geometry.coordinates.map((coordinates) => ({
    type: "Polygon",
    coordinates,
  }));
  const largest = parts.reduce((best, part) => (geoArea(part) > geoArea(best) ? part : best));
  return geoCentroid(largest);
}
