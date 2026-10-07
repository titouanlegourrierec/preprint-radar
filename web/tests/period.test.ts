import { describe, expect, it } from "vitest";
import {
  between,
  daysOverBudget,
  formatDays,
  isIsoDay,
  monthGrid,
  PAPER_BUDGET,
  periodKey,
  periodOfKey,
  samePeriod,
  selectDays,
  shiftMonth,
} from "../src/period";

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
    expect(selectDays(days, { kind: "recent", range: "40" })).toHaveLength(4);
  });

  it("keeps the days between two dates, inclusive", () => {
    expect(selectDays(days, between("2026-09-24", "2026-09-01")).map((day) => day.date)).toEqual([
      "2026-09-24",
      "2026-09-09",
      "2026-09-01",
    ]);
    expect(selectDays(days, between("2026-09-10", "2026-09-20"))).toEqual([]);
  });

  it("loads the latest days of a period within the paper budget", () => {
    // A year of days, 300 papers each: the budget holds the latest 33.
    const year = Array.from({ length: 250 }, (_, index) => ({
      date: `2026-${String(12 - Math.floor(index / 25)).padStart(2, "0")}-${String(28 - (index % 25)).padStart(2, "0")}`,
      count: 300,
    }));
    const period = between("2026-01-01", "2026-12-31");
    const loaded = selectDays(year, period);
    expect(loaded).toHaveLength(Math.floor(PAPER_BUDGET / 300));
    expect(loaded[0]).toEqual(year[0]);
    expect(daysOverBudget(year, period)).toBe(250 - loaded.length);
    expect(daysOverBudget(days, { kind: "recent", range: "40" })).toBe(0);
  });

  it("always loads the latest day, however large", () => {
    const huge = [{ date: "2026-09-25", count: PAPER_BUDGET + 1 }, ...days];
    expect(selectDays(huge, { kind: "recent", range: "5" })).toEqual([huge[0]]);
    expect(daysOverBudget(huge, { kind: "recent", range: "5" })).toBe(4);
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

describe("period keys", () => {
  it("are equal for equal periods, and give the period back", () => {
    const dates = between("2026-09-05", "2026-09-01");
    expect(periodKey(dates)).toBe("2026-09-01..2026-09-05");
    expect(periodKey({ kind: "recent", range: "20" })).toBe("20");
    expect(periodOfKey(periodKey(dates))).toEqual(dates);
    expect(periodOfKey("20")).toEqual({ kind: "recent", range: "20" });
    expect(periodKey(between("2026-09-01", "2026-09-05"))).toBe(periodKey(dates));
  });

  it("tell equal periods apart from others", () => {
    expect(samePeriod({ kind: "recent", range: "5" }, { kind: "recent", range: "5" })).toBe(true);
    expect(samePeriod({ kind: "recent", range: "5" }, between("2026-09-01", "2026-09-05"))).toBe(
      false,
    );
    expect(
      samePeriod(between("2026-09-01", "2026-09-05"), between("2026-09-01", "2026-09-05")),
    ).toBe(true);
    expect(samePeriod(between("2026-09-01", "2026-09-05"), { kind: "recent", range: "5" })).toBe(
      false,
    );
  });
});
