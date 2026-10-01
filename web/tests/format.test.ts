import { describe, expect, it } from "vitest";
import { citationsNote } from "../src/format";

describe("citationsNote", () => {
  const today = new Date("2026-10-01T12:00:00Z");

  it("gives the source and the date of the counts", () => {
    const note = citationsNote("Semantic Scholar", "2026-09-27T05:41:00+00:00", today);

    expect(note).toMatch(/^Citations on Semantic Scholar, as of /);
    expect(note).not.toMatch(/out of date/);
  });

  it("warns once the counts are older than two weeks", () => {
    expect(citationsNote("Semantic Scholar", "2026-09-10T05:41:00+00:00", today)).toMatch(
      / \(21 days ago: they may be out of date\)$/,
    );
  });
});
