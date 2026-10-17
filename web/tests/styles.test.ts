/** The palettes of `styles.css`, which CLAUDE.md asks to keep in step. */
import { describe, expect, it } from "vitest";
import html from "../index.html?raw";
import themeScript from "../public/theme.js?raw";
import css from "../src/styles.css?raw";
import { BACKGROUNDS } from "../src/theme-color";

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

  it("print black on white, over either theme (UX-18)", () => {
    const print = variables(":root:root");
    expect(css.indexOf(":root:root {")).toBeGreaterThan(css.indexOf(':root[data-theme="dark"] {'));
    expect([...print.keys()].filter((name) => !light.has(name))).toEqual([]);
    expect([print.get("--bg"), print.get("--text")]).toEqual(["#fff", "#000"]);
  });
});

describe("sizes (UX-16)", () => {
  const sizes = [...css.matchAll(/font-size:\s*([^;]+);/g)].map((match) => match[1] ?? "");

  it("write text in rem, from the reader's font size", () => {
    expect(sizes.filter((size) => size.endsWith("px"))).toEqual([]);
  });

  it("write no text under 11 px of the default 16", () => {
    const small = sizes.filter((size) => size.endsWith("rem") && Number.parseFloat(size) < 11 / 16);
    expect(small).toEqual([]);
  });
});

describe("the browser's bar (UX-18)", () => {
  const backgrounds = {
    light: variables(":root").get("--bg"),
    dark: variables(':root:not([data-theme="light"])').get("--bg"),
    forcedDark: variables(':root[data-theme="dark"]').get("--bg"),
  };
  // Each theme-color meta of index.html: its scheme (from `media`) and its color.
  const metas = [...html.matchAll(/<meta name="theme-color"([^>]*)>/g)].map(([, attributes]) => ({
    media: /media="([^"]*)"/.exec(attributes ?? "")?.[1],
    content: /content="([^"]*)"/.exec(attributes ?? "")?.[1],
  }));

  it("takes the page's background in each scheme", () => {
    expect(backgrounds).toEqual({
      light: BACKGROUNDS.light,
      dark: BACKGROUNDS.dark,
      forcedDark: BACKGROUNDS.dark,
    });
    expect(metas).toEqual([
      { media: "(prefers-color-scheme: light)", content: BACKGROUNDS.light },
      { media: "(prefers-color-scheme: dark)", content: BACKGROUNDS.dark },
    ]);
  });

  /** Runs `public/theme.js`, which index.html loads first, with `stored` as the remembered theme. */
  function restore(stored: string | null) {
    expect(html).toContain('<script src="/theme.js"></script>');
    const elements = metas.map(({ media, content }) => ({
      content: content ?? "",
      getAttribute: (name: string) => (name === "media" ? (media ?? null) : null),
    }));
    const root = { dataset: {} as Record<string, string> };
    const document = {
      documentElement: root,
      querySelectorAll: (selector: string) =>
        selector === 'meta[name="theme-color"]' ? elements : [],
    };
    const localStorage = { getItem: () => stored };
    new Function("document", "localStorage", themeScript)(document, localStorage);
    return { theme: root.dataset.theme, colors: elements.map(({ content }) => content) };
  }

  it("follows a theme forced by the toggle from first paint", () => {
    expect(restore(null)).toEqual({
      theme: undefined,
      colors: [BACKGROUNDS.light, BACKGROUNDS.dark],
    });
    expect(restore("dark")).toEqual({
      theme: "dark",
      colors: [BACKGROUNDS.dark, BACKGROUNDS.dark],
    });
    expect(restore("light")).toEqual({
      theme: "light",
      colors: [BACKGROUNDS.light, BACKGROUNDS.light],
    });
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
