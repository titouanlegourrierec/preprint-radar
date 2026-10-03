import type { DaySummary } from "./types";

/**
 * Most papers a period loads. Every paper of a period is downloaded and indexed in the
 * browser: a year of cs.CV (about 46,000 papers, 117 MB of JSON) takes 20 s to index and
 * about 480 MB of memory, which crashes phones; 10,000 papers stay near 100 MB. A longer
 * period loads its latest days up to this budget.
 */
export const PAPER_BUDGET = 10_000;

/**
 * Preset periods: the latest announcement days. The longest stays within the budget at
 * cs.CV's pace (about 185 papers a day, 7,400 in 40 days).
 */
export const RANGES = {
  "1": { label: "Latest day", days: 1 },
  "5": { label: "Last 5 days", days: 5 },
  "20": { label: "Last 20 days", days: 20 },
  "40": { label: "Last 40 days", days: 40 },
} as const;

export type RangeKey = keyof typeof RANGES;

/** The longest preset, which links to "All days" (`?range=all`, before the budget) open. */
export const LONGEST_RANGE: RangeKey = "40";

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
function periodDays(days: readonly DaySummary[], period: Period): DaySummary[] {
  return period.kind === "recent"
    ? days.slice(0, RANGES[period.range].days)
    : days.filter((day) => day.date >= period.from && day.date <= period.to);
}

/**
 * The days of the period to load (most recent first, as in the store index): its latest
 * ones within {@link PAPER_BUDGET}, and always its latest day, however large.
 */
export function selectDays(days: readonly DaySummary[], period: Period): DaySummary[] {
  const selected: DaySummary[] = [];
  let papers = 0;
  for (const day of periodDays(days, period)) {
    if (selected.length > 0 && papers + day.count > PAPER_BUDGET) break;
    selected.push(day);
    papers += day.count;
  }
  return selected;
}

/** How many days of the period {@link selectDays} leaves out for the budget. */
export function daysOverBudget(days: readonly DaySummary[], period: Period): number {
  return periodDays(days, period).length - selectDays(days, period).length;
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
