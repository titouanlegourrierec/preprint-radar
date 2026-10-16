import { describe, expect, it } from "vitest";
import lockup from "../public/preprint-radar-lockup.svg?raw";
import dark from "../public/preprint-radar-lockup-dark.svg?raw";
import light from "../public/preprint-radar-lockup-light.svg?raw";
import mark from "../public/preprint-radar-mark.svg?raw";
import { DOT, LOCKUP_VIEW_BOX, MARK_PATH, NAME_PATH, NAME_TRANSFORM } from "../src/logo";

/** The paths' `d` of an SVG file, in order. */
const paths = (svg: string) => [...svg.matchAll(/\sd="([^"]+)"/g)].map((match) => match[1]);

describe("the logo (UX-48)", () => {
  it("is drawn as its designer's files, never redrawn", () => {
    for (const file of [lockup, light, dark]) {
      expect(paths(file)).toEqual([MARK_PATH, NAME_PATH]);
      expect(file).toContain(`viewBox="${LOCKUP_VIEW_BOX}"`);
      expect(file).toContain(`<g transform="${NAME_TRANSFORM}">`);
      expect(file).toContain(`<circle cx="${DOT.cx}" cy="${DOT.cy}" r="${DOT.r}"`);
    }
    expect(paths(mark)).toEqual([MARK_PATH]);
    // The P is cut out of the square, which shows the background through it.
    expect(lockup).toContain('fill-rule="evenodd"');
  });
});
