import { describe, expect, it } from "vitest";
// The pipeline's tests (tests/unit/test_institutions.py) read the same cases, so that
// Python's `institutions.search_key` keys a name as the site does (AFF-24).
import foldCases from "../../tests/fixtures/fold-cases.json?raw";
import { fold, searchKey } from "../src/text";

const CASES: readonly { text: string; key: string }[] = JSON.parse(foldCases);

describe("searchKey", () => {
  it.each(CASES)("keys $text as $key, as Python does", ({ text, key }) => {
    expect(searchKey(text)).toBe(key);
  });
});

describe("fold", () => {
  it("drops accents and case, and keeps punctuation", () => {
    expect(fold("Lozano-Pérez, É.")).toBe("lozano-perez, e.");
  });

  it("writes ß as ss, whatever its case", () => {
    expect(fold("Nießner")).toBe(fold("NIESSNER"));
    expect(fold("GROẞE Straße")).toBe("grosse strasse");
  });
});
