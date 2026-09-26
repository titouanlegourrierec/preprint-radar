import { describe, expect, it } from "vitest";
import { between, formatDays, isIsoDay, monthGrid, selectDays, shiftMonth } from "../src/period";

const days = [
  { date: "2026-09-25", count: 143 },
  { date: "2026-09-24", count: 128 },
  { date: "2026-09-09", count: 361 },
  { date: "2026-09-01", count: 316 },
];

describe("selectDays", () => {
  it("keeps the latest days of a preset", () => {
    expect(selectDays(days, { kind: "recent", range: "1" }).map((day) => day.date)).toEqual([
      "2026-09-25",
    ]);
    expect(selectDays(days, { kind: "recent", range: "all" })).toHaveLength(4);
  });

  it("keeps the days between two dates, inclusive", () => {
    expect(selectDays(days, between("2026-09-24", "2026-09-01")).map((day) => day.date)).toEqual([
      "2026-09-24",
      "2026-09-09",
      "2026-09-01",
    ]);
    expect(selectDays(days, between("2026-09-10", "2026-09-20"))).toEqual([]);
  });
});

describe("calendar helpers", () => {
  it("lays out a month in weeks starting on Monday", () => {
    const weeks = monthGrid("2026-09");
    // 1 September 2026 is a Tuesday, the 30th a Wednesday.
    expect(weeks).toHaveLength(5);
    expect(weeks[0]?.slice(0, 2)).toEqual([null, "2026-09-01"]);
    expect(weeks[4]).toEqual(["2026-09-28", "2026-09-29", "2026-09-30", null, null, null, null]);
  });

  it("moves between months across years", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
  });

  it("validates ISO days", () => {
    expect(isIsoDay("2026-09-09")).toBe(true);
    expect(isIsoDay("2026-9-9")).toBe(false);
    expect(isIsoDay(null)).toBe(false);
  });

  it("formats a day or a range", () => {
    expect(formatDays("2026-09-09", "2026-09-09")).toMatch(/9/);
    expect(formatDays("2026-09-09", "2026-09-18")).toMatch(/9.*18/);
  });
});
