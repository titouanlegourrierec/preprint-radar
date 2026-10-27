import { describe, expect, it } from "vitest";
import { moveMark, moveText, rankMoves } from "../src/moves";

describe("rankMoves", () => {
  it("says how many places each row moved, up positive, null for a newcomer (UX-62)", () => {
    const moves = rankMoves(["a", "b", "c", "d"], ["c", "a", "b", "e"]);
    expect([...moves]).toEqual([
      ["c", 2],
      ["a", -1],
      ["b", -1],
      ["e", null],
    ]);
  });
});

describe("moveMark", () => {
  it("draws a move by the rank", () => {
    expect(moveMark(12)).toBe("▲12");
    expect(moveMark(-3)).toBe("▼3");
    expect(moveMark(null)).toBe("new");
    expect(moveMark(0)).toBe("");
    expect(moveMark(undefined)).toBe("");
  });
});

describe("moveText", () => {
  it("says a move to screen readers", () => {
    expect(moveText(5, "the 90 days")).toBe(", up 5 places from the 90 days");
    expect(moveText(-1, "the 12 months")).toBe(", down 1 place from the 12 months");
    expect(moveText(null, "the 90 days")).toBe(", new in this list");
    expect(moveText(0, "the 90 days")).toBe("");
  });
});
