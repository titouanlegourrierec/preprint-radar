import type { DaySummary } from "./types";

/** Preset periods: the latest announcement days. */
export const RANGES = {
  "1": { label: "Latest day", days: 1 },
  "5": { label: "Last 5 days", days: 5 },
  "20": { label: "Last 20 days", days: 20 },
  all: { label: "All days", days: Number.POSITIVE_INFINITY },
} as const;

export type RangeKey = keyof typeof RANGES;

/** Papers to show: the latest announcement days, or the days between two dates. */
export type Period =
  | { kind: "recent"; range: RangeKey }
  | {
      kind: "dates";
      /** First day, as an ISO date. */
      from: string;
      /** Last day, inclusive. */
      to: string;
    };

export type DateRange = Extract<Period, { kind: "dates" }>;

export const DEFAULT_PERIOD: Period = { kind: "recent", range: "5" };

const ISO_DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isRange(value: string | null): value is RangeKey {
  return value !== null && Object.hasOwn(RANGES, value);
}

export function isIsoDay(value: string | null): value is string {
  return value !== null && ISO_DAY_RE.test(value) && !Number.isNaN(Date.parse(value));
}

/** A period between two days, given in any order. */
export function between(first: string, second: string): DateRange {
  return first <= second
    ? { kind: "dates", from: first, to: second }
    : { kind: "dates", from: second, to: first };
}

/** Days of `days` (most recent first, as in the store index) that fall in the period. */
export function selectDays(days: readonly DaySummary[], period: Period): DaySummary[] {
  return period.kind === "recent"
    ? days.slice(0, RANGES[period.range].days)
    : days.filter((day) => day.date >= period.from && day.date <= period.to);
}

export function samePeriod(a: Period, b: Period): boolean {
  return a.kind === "recent"
    ? b.kind === "recent" && a.range === b.range
    : b.kind === "dates" && a.from === b.from && a.to === b.to;
}

/** Local midnight of an ISO day, for display. */
export function dayDate(iso: string): Date {
  return new Date(`${iso}T00:00:00`);
}

export function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** "YYYY-MM" of an ISO day. */
export function monthOf(iso: string): string {
  return iso.slice(0, 7);
}

/** The month before or after `month` ("YYYY-MM"). */
export function shiftMonth(month: string, offset: number): string {
  const [year = 1970, index = 1] = month.split("-").map(Number);
  return isoDay(new Date(year, index - 1 + offset, 1)).slice(0, 7);
}

/**
 * The days of a month ("YYYY-MM") as calendar rows, weeks starting on Monday; `null` pads
 * the first and last weeks.
 */
export function monthGrid(month: string): (string | null)[][] {
  const [year = 1970, index = 1] = month.split("-").map(Number);
  const first = new Date(year, index - 1, 1);
  const length = new Date(year, index, 0).getDate();
  const cells: (string | null)[] = Array.from({ length: (first.getDay() + 6) % 7 }, () => null);
  for (let day = 1; day <= length; day++) cells.push(isoDay(new Date(year, index - 1, day)));
  while (cells.length % 7 !== 0) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, week) => cells.slice(week * 7, week * 7 + 7));
}

const DAY_FORMAT = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** "9 – 18 Sept 2026", or a single day. */
export function formatDays(from: string, to: string): string {
  return from === to
    ? DAY_FORMAT.format(dayDate(from))
    : DAY_FORMAT.formatRange(dayDate(from), dayDate(to));
}
