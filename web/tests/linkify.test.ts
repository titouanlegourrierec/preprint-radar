import { describe, expect, it } from "vitest";
import { linkify } from "../src/linkify";

describe("linkify", () => {
  it("returns plain text unchanged", () => {
    expect(linkify("No links here.")).toEqual([{ text: "No links here." }]);
  });

  it("extracts URLs in the middle of a sentence", () => {
    expect(linkify("Code: https://github.com/a/b and more")).toEqual([
      { text: "Code: " },
      { text: "https://github.com/a/b", url: "https://github.com/a/b" },
      { text: " and more" },
    ]);
  });

  it("leaves sentence punctuation outside the link", () => {
    expect(linkify("See https://x.io/y. Next").map((part) => part.url ?? null)).toEqual([
      null,
      "https://x.io/y",
      null,
    ]);
  });

  it("keeps balanced parentheses but drops a closing one", () => {
    expect(linkify("(https://en.wikipedia.org/wiki/A_(b))")[1]?.url).toBe(
      "https://en.wikipedia.org/wiki/A_(b)",
    );
    expect(linkify("(project: https://x.io/p)")[1]?.url).toBe("https://x.io/p");
  });

  it("keeps brackets that belong to the URL, and drops those of the sentence", () => {
    expect(linkify("(see https://x.io/a_(b))")).toEqual([
      { text: "(see " },
      { text: "https://x.io/a_(b)", url: "https://x.io/a_(b)" },
      { text: ")" },
    ]);
    expect(linkify("[code: https://github.com/x/y].")).toEqual([
      { text: "[code: " },
      { text: "https://github.com/x/y", url: "https://github.com/x/y" },
      { text: "]." },
    ]);
  });

  it("skips a scheme without an address", () => {
    expect(linkify("http://. done")).toEqual([{ text: "http://. done" }]);
  });
});
