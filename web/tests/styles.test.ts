/** The palettes of `styles.css`, which CLAUDE.md asks to keep in step. */
import { describe, expect, it } from "vitest";
import css from "../src/styles.css?raw";

/** The custom properties of the first block that `selector` opens. */
function variables(selector: string): Map<string, string> {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("}", start));
  return new Map(
    [...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [match[1] ?? "", match[2] ?? ""]),
  );
}

describe("palettes", () => {
  const light = variables(":root");
  const systemDark = variables(':root:not([data-theme="light"])');
  const forcedDark = variables(':root[data-theme="dark"]');

  it("declare the dark palette twice, identically", () => {
    expect(systemDark.size).toBeGreaterThan(10);
    expect([...systemDark]).toEqual([...forcedDark]);
  });

  it("give every color of the light palette a dark value", () => {
    const colors = [...light].filter(([, value]) => value.startsWith("#")).map(([name]) => name);
    expect(colors.filter((name) => !systemDark.has(name))).toEqual([]);
  });
});

describe("links inside text", () => {
  // The selectors of the rule that underlines them: every class of running text with links.
  const rule = css.slice(
    css.indexOf(".paper__abstract a,"),
    css.indexOf("}", css.indexOf(".paper__abstract a,")),
  );

  it("are underlined wherever text holds them", () => {
    for (const selector of [
      ".paper__abstract a",
      ".paper__comments a",
      ".paper__elsewhere a",
      ".paper__report a",
      ".site-footer a",
      ".about a",
      ".notice a",
      ".feed-link a",
      ".graph__counts a",
    ]) {
      expect(rule).toContain(`${selector}`);
    }
    expect(rule).toContain("text-decoration: underline");
  });
});
