import { describe, expect, it } from "vitest";
import { Highlighted } from "../src/components/Highlighted";
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

  it("marks ß and ss alike, which fold longer than their characters", () => {
    expect(marked("Matthias Nießner and Niessner", ["niessner"])).toEqual(["Nießner", "Niessner"]);
    expect(marked("Matthias Niessner", ["Nießner"])).toEqual(["Niessner"]);
    expect(
      highlight("Matthias Nießner, TUM", ["niessner"])
        .map((s) => s.text)
        .join(""),
    ).toBe("Matthias Nießner, TUM");
  });

  it("returns the text unchanged without terms", () => {
    expect(highlight("Some text", [])).toEqual([{ text: "Some text", match: false }]);
  });
});

describe("Highlighted", () => {
  // Its marks, each with its key, from the fragment it returns.
  const marks = (text: string, terms: string[]) => {
    const fragment = Highlighted({ text, terms }) as unknown as { props: { children: unknown[] } };
    return fragment.props.children
      .filter((child) => typeof child === "object" && child !== null)
      .map((child) => {
        const mark = child as { key: unknown; props: { children: unknown } };
        return [mark.key, mark.props.children];
      });
  };

  it("keys a mark by where it starts: one shown stays when a word is found before it (UX-56)", () => {
    expect(marks("Fast Gaussian Splatting", ["gaussian"])).toEqual([[5, "Gaussian"]]);
    expect(marks("Fast Gaussian Splatting", ["fast", "gaussian"])).toEqual([
      [0, "Fast"],
      [5, "Gaussian"],
    ]);
  });
});
