import { describe, expect, it } from "vitest";
import { highlight } from "../src/highlight";

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
