import { describe, expect, it } from "vitest";
import { applyThemeColor, BACKGROUNDS } from "../src/theme-color";

/** index.html's two metas, as the toggle finds them. */
function metas() {
  return ["(prefers-color-scheme: light)", "(prefers-color-scheme: dark)"].map((media) => ({
    content: "",
    getAttribute: (name: string) => (name === "media" ? media : null),
  }));
}

describe("applyThemeColor", () => {
  it("gives each scheme its background while the theme follows the system", () => {
    const shown = metas();
    applyThemeColor(shown, "auto");
    expect(shown.map(({ content }) => content)).toEqual([BACKGROUNDS.light, BACKGROUNDS.dark]);
  });

  it("gives both schemes the background of a forced theme", () => {
    const shown = metas();
    applyThemeColor(shown, "dark");
    expect(shown.map(({ content }) => content)).toEqual([BACKGROUNDS.dark, BACKGROUNDS.dark]);
    applyThemeColor(shown, "light");
    expect(shown.map(({ content }) => content)).toEqual([BACKGROUNDS.light, BACKGROUNDS.light]);
    applyThemeColor(shown, "auto");
    expect(shown.map(({ content }) => content)).toEqual([BACKGROUNDS.light, BACKGROUNDS.dark]);
  });
});
