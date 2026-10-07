import { describe, expect, it } from "vitest";
import { nextFocusIndex, nextPage, PAGE_SIZE, pageCount } from "../src/paging";

describe("pageCount", () => {
  it("starts a new list over at one page", () => {
    expect(pageCount({ keyChanged: true, visible: 120, targetIndex: -1 })).toBe(PAGE_SIZE);
  });

  it("keeps the cards shown for the same list", () => {
    expect(pageCount({ keyChanged: false, visible: 120, targetIndex: -1 })).toBe(120);
    expect(pageCount({ keyChanged: false, visible: 0, targetIndex: -1 })).toBe(PAGE_SIZE);
  });

  it("reaches a shared link's target", () => {
    expect(pageCount({ keyChanged: true, visible: 40, targetIndex: 85 })).toBe(120);
    expect(pageCount({ keyChanged: false, visible: 160, targetIndex: 85 })).toBe(160);
    expect(pageCount({ keyChanged: true, visible: 40, targetIndex: 39 })).toBe(PAGE_SIZE);
  });
});

describe("nextFocusIndex", () => {
  it("is the card now at the place of the one that left, else the last", () => {
    expect(nextFocusIndex(10, 4)).toBe(4);
    expect(nextFocusIndex(4, 4)).toBe(3);
    expect(nextFocusIndex(0, 0)).toBe(-1);
    expect(nextFocusIndex(3, -1)).toBe(0);
  });
});

describe("nextPage", () => {
  it("adds a page while cards are left, never to an empty list or one shown whole", () => {
    expect(nextPage(40, 1016)).toBe(80);
    expect(nextPage(40, 0)).toBe(40);
    expect(nextPage(40, 23)).toBe(40);
    expect(nextPage(1000, 1016)).toBe(1040);
  });
});
