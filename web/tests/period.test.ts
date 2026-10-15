import { describe, expect, it } from "vitest";
import {
  between,
  daysOverBudget,
  formatDays,
  formatMissingDays,
  formatMonth,
  isIsoDay,
  LIGHT_BUDGET,
  lightDays,
  monthGrid,
  monthOf,
  PAPER_BUDGET,
  periodKey,
  periodOfKey,
  rangeOf,
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
    expect(selectDays(days, { kind: "recent", range: "day" }).map((day) => day.date)).toEqual([
      "2026-09-25",
    ]);
    expect(selectDays(days, { kind: "recent", range: "month" })).toHaveLength(4);
  });

  it("keeps the days between two dates, inclusive", () => {
    expect(selectDays(days, between("2026-09-24", "2026-09-01")).map((day) => day.date)).toEqual([
      "2026-09-24",
      "2026-09-09",
      "2026-09-01",
    ]);
    expect(selectDays(days, between("2026-09-10", "2026-09-20"))).toEqual([]);
  });

  it("keeps the days since a day, to the latest (PROD-13)", () => {
    expect(selectDays(days, { kind: "since", from: "2026-09-09" }).map(({ date }) => date)).toEqual(
      ["2026-09-25", "2026-09-24", "2026-09-09"],
    );
    expect(selectDays(days, { kind: "since", from: "2026-09-26" })).toEqual([]);
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
    // The older days from the search shards, within their own budget; the rest left out.
    const light = lightDays(year, period);
    expect(light).toHaveLength(Math.floor(LIGHT_BUDGET / 300));
    expect(light[0]).toEqual(year[loaded.length]);
    expect(daysOverBudget(year, period)).toBe(250 - loaded.length - light.length);
    expect(daysOverBudget(days, { kind: "recent", range: "month" })).toBe(0);
    expect(lightDays(days, { kind: "recent", range: "month" })).toEqual([]);
  });

  it("always loads the latest day, however large", () => {
    const huge = [{ date: "2026-09-26", count: PAPER_BUDGET + 1 }, ...days];
    expect(selectDays(huge, { kind: "recent", range: "month" })).toEqual([huge[0]]);
    expect(lightDays(huge, { kind: "recent", range: "month" })).toEqual(days);
    expect(daysOverBudget(huge, { kind: "recent", range: "month" })).toBe(0);
  });

  it("counts a preset in calendar days to the latest announcement day (SRCH-14)", () => {
    // A week to Friday 25 September holds its five weekdays; one with a holiday, four.
    const weekdays = ["2026-09-25", "2026-09-24", "2026-09-23", "2026-09-22", "2026-09-21"];
    const announced = [...weekdays, "2026-09-18"].map((date) => ({ date, count: 100 }));
    const week = { kind: "recent", range: "week" } as const;
    expect(selectDays(announced, week).map((day) => day.date)).toEqual(weekdays);
    const holiday = announced.filter((day) => day.date !== "2026-09-21");
    expect(selectDays(holiday, week)).toHaveLength(4);
    expect(selectDays(days, { kind: "recent", range: "week" })).toHaveLength(2);
    expect(selectDays([], week)).toEqual([]);
  });

  it("opens the presets of former links as the ones that hold as many days", () => {
    expect(rangeOf("week")).toBe("week");
    expect(rangeOf("1")).toBe("day");
    expect(rangeOf("5")).toBe("week");
    expect(rangeOf("20")).toBe("month");
    expect(rangeOf("40")).toBe("month");
    expect(rangeOf("all")).toBe("month");
    expect(rangeOf("42")).toBeNull();
    expect(rangeOf("toString")).toBeNull();
    expect(rangeOf(null)).toBeNull();
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
    expect(periodKey({ kind: "recent", range: "month" })).toBe("month");
    expect(periodOfKey(periodKey(dates))).toEqual(dates);
    expect(periodOfKey("month")).toEqual({ kind: "recent", range: "month" });
    expect(periodKey(between("2026-09-01", "2026-09-05"))).toBe(periodKey(dates));
    const since = { kind: "since" as const, from: "2026-09-15" };
    expect(periodKey(since)).toBe("2026-09-15..");
    expect(periodOfKey(periodKey(since))).toEqual(since);
  });

  it("tell equal periods apart from others", () => {
    expect(samePeriod({ kind: "recent", range: "week" }, { kind: "recent", range: "week" })).toBe(
      true,
    );
    expect(samePeriod({ kind: "recent", range: "week" }, between("2026-09-01", "2026-09-05"))).toBe(
      false,
    );
    expect(
      samePeriod(between("2026-09-01", "2026-09-05"), between("2026-09-01", "2026-09-05")),
    ).toBe(true);
    expect(samePeriod(between("2026-09-01", "2026-09-05"), { kind: "recent", range: "week" })).toBe(
      false,
    );
    const since = { kind: "since" as const, from: "2026-09-01" };
    expect(samePeriod(since, { ...since })).toBe(true);
    expect(samePeriod(since, between("2026-09-01", "2026-09-25"))).toBe(false);
  });
});

describe("formatMonth", () => {
  it("names a month in full", () => {
    expect(formatMonth("2026-09")).toBe(
      new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(
        new Date(2026, 8, 1),
      ),
    );
  });
});

describe("formatMissingDays", () => {
  it("names one or two days, and counts more over their span", () => {
    expect(formatMissingDays(["2026-09-25"])).toBe(formatDays("2026-09-25", "2026-09-25"));
    expect(formatMissingDays(["2026-09-25", "2026-09-24"])).toBe(
      `${formatDays("2026-09-24", "2026-09-24")} and ${formatDays("2026-09-25", "2026-09-25")}`,
    );
    expect(formatMissingDays(["2026-09-30", "2026-09-01", "2026-09-14"])).toBe(
      `3 days in ${formatDays("2026-09-01", "2026-09-30")}`,
    );
  });
});

describe("monthOf", () => {
  it("is the month of an ISO day", () => {
    expect(monthOf("2026-09-25")).toBe("2026-09");
  });
});
