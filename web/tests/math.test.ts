import { describe, expect, it } from "vitest";
import { drawableTex, textPieces, withoutStyles } from "../src/math";

const words = (text: string) => ({ text, math: false });
const formula = (text: string) => ({ text, math: true });

describe("textPieces (UX-69)", () => {
  it("finds the formulas between dollars", () => {
    expect(textPieces("ResNet$^2$: deeper")).toEqual([
      words("ResNet"),
      formula("^2"),
      words(": deeper"),
    ]);
    expect(textPieces("an $ℓ_1$ loss and $O(N^2)$ time")).toEqual([
      words("an "),
      formula("ℓ_1"),
      words(" loss and "),
      formula("O(N^2)"),
      words(" time"),
    ]);
    expect(textPieces("$x$")).toEqual([formula("x")]);
    expect(textPieces("as $$\\frac{a}{b}$$ shows")).toEqual([
      words("as "),
      formula("\\frac{a}{b}"),
      words(" shows"),
    ]);
  });

  it("keeps dollars that open no formula as words", () => {
    expect(textPieces("costs $20,000 and $30,000")).toEqual([words("costs $20,000 and $30,000")]);
    expect(textPieces("a $5 budget")).toEqual([words("a $5 budget")]);
    expect(textPieces("spaced $ x $ dollars")).toEqual([words("spaced $ x $ dollars")]);
    expect(textPieces("escaped \\$5 and \\$6")).toEqual([words("escaped \\$5 and \\$6")]);
    expect(textPieces("")).toEqual([words("")]);
  });
});

describe("withoutStyles", () => {
  it("drops the style attributes the policy refuses, and keeps MathML's own", () => {
    expect(
      withoutStyles('<math><mi style="color:#ff0000;">x</mi><mo stretchy="false">ˆ</mo></math>'),
    ).toBe('<math><mi>x</mi><mo stretchy="false">ˆ</mo></math>');
  });
});

describe("drawableTex", () => {
  it("escapes the percent signs TeX would take for a comment", () => {
    expect(drawableTex("86{-}98%")).toBe("86{-}98\\%");
    expect(drawableTex("10\\% of x")).toBe("10\\% of x");
  });
});
