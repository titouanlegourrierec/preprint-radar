import { describe, expect, it } from "vitest";
import { linkOuts } from "../src/link-outs";

describe("linkOuts", () => {
  it("build each tool's address from the arXiv id", () => {
    expect(linkOuts("2609.31620").map(({ name, url }) => [name, url])).toEqual([
      ["Semantic Scholar", "https://api.semanticscholar.org/arXiv:2609.31620"],
      ["Connected Papers", "https://www.connectedpapers.com/api/redirect/arxiv/2609.31620"],
      ["alphaXiv", "https://www.alphaxiv.org/abs/2609.31620"],
    ]);
  });

  it("say what each one gives", () => {
    for (const link of linkOuts("2609.31620")) expect(link.title).toContain(link.name);
  });
});
