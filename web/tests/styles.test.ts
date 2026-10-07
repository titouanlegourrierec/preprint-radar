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

describe("buttons inside text", () => {
  it("are underlined as links are", () => {
    const start = css.indexOf(".notice .link-button,");
    const rule = css.slice(start, css.indexOf("}", start));
    expect(rule).toContain(".graph__focus .link-button");
    expect(rule).toContain("text-decoration: underline");
  });
});

describe("focus rings", () => {
  // Each innermost rule, its selector and its declarations (a media query's rules included).
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: (match[1] ?? "").replace(/\/\*[\s\S]*?\*\//g, "").trim(),
    body: match[2] ?? "",
  }));

  it("are never taken away from a focused control (UX-9)", () => {
    // A rule on `:focus`, or a later one as specific as `:focus-visible`, outranks the ring:
    // it may restyle it, not remove it. The search box alone draws its own (below).
    const removing = rules.filter(
      ({ selector, body }) =>
        !selector.includes(":not(:focus-visible)") &&
        /outline(?:-style|-width|-color)?:[^;]*?(?:\bnone\b|\btransparent\b|(?<![\d.\w-])0(?:px)?(?![\d.\w%-]))/.test(
          body,
        ),
    );
    expect(rules.length).toBeGreaterThan(100);
    expect(removing.map(({ selector }) => selector)).toEqual([".search__input"]);
  });

  it("show on the search box as a shadow, and an outline where shadows are dropped", () => {
    const own = rules.filter(({ selector }) => selector === ".search__input:focus");
    expect(own.map(({ body }) => body).join("")).toContain("box-shadow: 0 0 0 3px");
    const forced = css.indexOf("@media (forced-colors: active) {\n  .search__input:focus {");
    expect(forced).toBeGreaterThan(-1);
    expect(css.slice(forced, css.indexOf("}", forced))).toContain("outline: 2px solid CanvasText");
  });
});
