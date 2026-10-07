import { describe, expect, it } from "vitest";
import { highlight, wholeWord, wordStarts } from "../src/highlight";

const marked = (text: string, terms: string[]) =>
  highlight(text, terms)
    .filter((segment) => segment.match)
    .map((segment) => segment.text);

describe("highlight", () => {
  it("marks whole words starting with a term", () => {
    expect(marked("Gaussian splatting and splats", ["splat"])).toEqual(["splatting", "splats"]);
  });

  it("marks a phrase whatever separates its words", () => {
    expect(marked("Self-Supervised and self supervised", ["self supervised"])).toEqual([
      "Self-Supervised",
      "self supervised",
    ]);
  });

  it("marks whole words only for a term made by wholeWord", () => {
    expect(
      marked("ViT and vitamins, Self-Supervised", [wholeWord("vit"), wholeWord("self supervised")]),
    ).toEqual(["ViT", "Self-Supervised"]);
  });

  it("marks every word start for a term made by wordStarts, a plain term's inner words whole", () => {
    expect(marked("John Smith and Jo Smithson", [wordStarts("j smith")])).toEqual([
      "John Smith",
      "Jo Smithson",
    ]);
    expect(marked("John Smith", ["j smith"])).toEqual([]);
  });

  it("does not match inside words", () => {
    expect(marked("Unsplattable", ["splat"])).toEqual([]);
  });

  it("is accent-insensitive and preserves the original text", () => {
    expect(marked("Tomás Lozano-Pérez", ["perez"])).toEqual(["Pérez"]);
    expect(
      highlight("Tomás Lozano-Pérez", ["perez"])
        .map((s) => s.text)
        .join(""),
    ).toBe("Tomás Lozano-Pérez");
  });

  it("returns the text unchanged without terms", () => {
    expect(highlight("Some text", [])).toEqual([{ text: "Some text", match: false }]);
  });
});
