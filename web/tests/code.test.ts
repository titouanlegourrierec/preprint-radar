import { describe, expect, it } from "vitest";
import { codeUrl } from "../src/code";

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
