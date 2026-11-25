import { describe, expect, it } from "vitest";
import page from "../index.html?raw";
import manifest from "../public/manifest.webmanifest?raw";
import { categoryTitle, listed } from "../src/format";
import { describing, FOLLOWED } from "../tooling/description";

describe("the site's description (ARCH-4)", () => {
  it("names the categories the store holds, in the page and the manifest", () => {
    for (const text of [page, manifest]) {
      expect(text).toContain(FOLLOWED);
      const both = describing(text, ["cs.CV", "cs.LG"]);
      expect(both).toContain("the cs.CV and cs.LG papers");
      expect(both).not.toContain(FOLLOWED);
      expect(describing(text, ["cs.CV"])).toBe(text);
    }
    // Without an index (a build without data), as written.
    expect(describing(page, [])).toBe(page);
  });

  it("fails on a text that no longer says what it follows", () => {
    expect(() => describing("Follow the computer vision papers.", ["cs.CV"])).toThrow(FOLLOWED);
  });

  it("lists names and titles as About says them", () => {
    expect(listed([])).toBe("");
    expect(listed(["a"])).toBe("a");
    expect(listed(["a", "b"])).toBe("a and b");
    expect(listed(["a", "b", "c"])).toBe("a, b and c");
    expect(categoryTitle("cs.LG")).toBe("Machine Learning (cs.LG)");
    expect(categoryTitle("q-bio.QM")).toBe("q-bio.QM");
  });
});
