import { describe, expect, it } from "vitest";
import codeCases from "../../tests/fixtures/code-cases.json?raw";
import { codeBadge, codeHost, codeUrl } from "../src/code";

const paper = (abstract: string | null, comments: string | null = null) => ({
  abstract,
  comments,
});

describe("codeUrl", () => {
  it("finds the repository an abstract or its comments link", () => {
    expect(codeUrl(paper("Code is available at https://github.com/example/splat."))).toBe(
      "https://github.com/example/splat",
    );
    expect(codeUrl(paper(null, "10 pages. Code: https://gitlab.com/lab/tool/-/tree/main"))).toBe(
      "https://gitlab.com/lab/tool/-/tree/main",
    );
    expect(codeUrl(paper("See http://www.github.com/example/old"))).toBe(
      "http://www.github.com/example/old",
    );
  });

  it("prefers a repository to models or data on the Hub", () => {
    expect(
      codeUrl(
        paper(
          "Data: https://huggingface.co/datasets/example/set.",
          "Code: https://github.com/example/model",
        ),
      ),
    ).toBe("https://github.com/example/model");
    expect(codeUrl(paper("Weights at https://huggingface.co/example/model."))).toBe(
      "https://huggingface.co/example/model",
    );
  });

  it("is not a user's page, a project page or the Hub's page of the paper", () => {
    expect(codeUrl(paper("Code: https://github.com/example/"))).toBeNull();
    expect(codeUrl(paper("Project page: https://example.github.io/splat"))).toBeNull();
    expect(
      codeUrl(paper("https://huggingface.co/papers/2610.01234 and https://huggingface.co/lab")),
    ).toBeNull();
    expect(codeUrl(paper("No link here", null))).toBeNull();
    expect(codeUrl(paper(null))).toBeNull();
  });

  it("reads a record once", () => {
    const record = paper("Code: https://github.com/example/once");
    expect(codeUrl(record)).toBe("https://github.com/example/once");
    record.abstract = "changed";
    expect(codeUrl(record)).toBe("https://github.com/example/once");
  });
});

describe("codeUrl and the pipeline", () => {
  // The same cases as tests/unit/test_code.py: a paper's stars are those of its card's link.
  const cases = JSON.parse(codeCases) as {
    abstract: string;
    comments?: string;
    url: string | null;
    host?: string;
  }[];

  it.each(cases)("finds $url", ({ abstract, comments, url, host }) => {
    expect(codeUrl(paper(abstract, comments ?? null))).toBe(url);
    // The site its card's logo names (UX-28) is the one the pipeline asks for the stars.
    expect(url === null ? undefined : codeHost(url)).toBe(host);
  });
});

describe("codeBadge", () => {
  it("says the stars, those gained this week, and whether they are shared", () => {
    expect(codeBadge({ stars: 1234, gained: 12 })).toEqual({
      count: "1,234",
      symbol: "★",
      noun: "GitHub stars",
      gained: "+12 this week",
      shared: false,
      title: "1,234 stars on GitHub, refreshed every week. 12 stars gained in the last week.",
    });
    const shared = codeBadge({ stars: 1, shared: true });
    expect(shared).toMatchObject({ count: "1", noun: "GitHub star", gained: null, shared: true });
    expect(shared?.title).toContain("not this paper's alone");
  });

  it("says the likes of a page on the Hub", () => {
    expect(codeBadge({ likes: 1 })).toMatchObject({
      symbol: "♥",
      noun: "Hugging Face like",
      title: "1 like on Hugging Face, refreshed every week.",
    });
    expect(codeBadge({ likes: 3 })?.noun).toBe("Hugging Face likes");
  });

  it("is nothing without counts", () => {
    expect(codeBadge(undefined)).toBeNull();
    expect(codeBadge({})).toBeNull();
  });
});
