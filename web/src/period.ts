import type { DaySummary } from "./types";

/**
 * Most papers a period loads whole. Every paper of a period is downloaded and indexed in
 * the browser: a year of cs.CV (about 46,000 papers, 117 MB of JSON) takes 20 s to index and
 * about 480 MB of memory, which crashes phones; 10,000 papers stay near 100 MB. A longer
 * period loads its latest days whole up to this budget, and its older ones from the search
 * shards ({@link LIGHT_BUDGET}). The smoke test builds the site with a smaller one
 * (`VITE_PAPER_BUDGET`), to read a period past it.
 */
export const PAPER_BUDGET = Number(import.meta.env.VITE_PAPER_BUDGET) || 10_000;

/**
 * Most papers a period loads from the search shards (`search-shards.ts`), past
 * {@link PAPER_BUDGET}: without abstracts, 5,857 papers took 0.3 s to index and 29 MB
 * (1.6 s and 77 MB whole, PERF-1), so that about seven months are searched in all.
 */
export const LIGHT_BUDGET = 20_000;

/**
 * Preset periods: the announcement days of the last calendar days to the latest one
 * (SRCH-14), whose names say what they hold: "Last 5 days" counted announcement days, a
 * calendar week. A week holds five, fewer after a holiday, and a month about 22 (4,300
 * papers at cs.CV's pace of about 195 a day), well within the budget; the calendar picks
 * any other period.
 */
export const RANGES = {
  day: { label: "Latest day", calendarDays: 1 },
  week: { label: "Last week", calendarDays: 7 },
  month: { label: "Last month", calendarDays: 30 },
} as const;

export type RangeKey = keyof typeof RANGES;

/** The longest preset, which links to "All days" (`?range=all`, before the budget) open. */
export const LONGEST_RANGE: RangeKey = "month";

/**
 * The presets of former links, counted in announcement days ("Last 5 days"): each opens
 * the one that holds as many days, and "All days" the longest.
 */
const FORMER_RANGES: Record<string, RangeKey> = {
  "1": "day",
  "5": "week",
  "20": "month",
  "40": "month",
  all: LONGEST_RANGE,
};

/**
 * Papers to show: the latest announcement days, the days between two dates, or those since
 * a date, to the latest day (`?since=`, PROD-13), which a bookmark keeps following.
 */
export type Period =
  | { kind: "recent"; range: RangeKey }
  | {
      kind: "dates";
      /** First day, as an ISO date. */
      from: string;
      /** Last day, inclusive. */
      to: string;
    }
  | {
      kind: "since";
      /** First day, as an ISO date. */
      from: string;
    };

export type DateRange = Extract<Period, { kind: "dates" }>;

export const DEFAULT_PERIOD: Period = { kind: "recent", range: "week" };

const ISO_DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isRange(value: string | null): value is RangeKey {
  return value !== null && Object.hasOwn(RANGES, value);
}

/** The preset a link's `range` names, a former one's included; `null` for none. */
export function rangeOf(value: string | null): RangeKey | null {
  if (isRange(value)) return value;
  return (value !== null && Object.hasOwn(FORMER_RANGES, value) && FORMER_RANGES[value]) || null;
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
  if (period.kind === "dates") {
    return days.filter((day) => day.date >= period.from && day.date <= period.to);
  }
  if (period.kind === "since") return days.filter((day) => day.date >= period.from);
  const latest = days[0]?.date;
  if (latest === undefined) return [];
  const first = dayDate(latest);
  first.setDate(first.getDate() - (RANGES[period.range].calendarDays - 1));
  const from = isoDay(first);
  return days.filter((day) => day.date >= from);
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

/**
 * The days of the period older than those {@link selectDays} keeps, which load from the
 * search shards: as many as {@link LIGHT_BUDGET} allows, most recent first.
 */
export function lightDays(days: readonly DaySummary[], period: Period): DaySummary[] {
  const older = periodDays(days, period).slice(selectDays(days, period).length);
  const light: DaySummary[] = [];
  let papers = 0;
  for (const day of older) {
    if (papers + day.count > LIGHT_BUDGET) break;
    light.push(day);
    papers += day.count;
  }
  return light;
}

/** How many days of the period are left out past both budgets, whole and light. */
export function daysOverBudget(days: readonly DaySummary[], period: Period): number {
  return (
    periodDays(days, period).length -
    selectDays(days, period).length -
    lightDays(days, period).length
  );
}

/**
 * A period as text, the same for equal periods ("week", "2026-09-01..2026-09-05",
 * "2026-09-15.." since a day): what makes `usePapers` load again, since the URL gives a new
 * object for the same period at each reading (Back, a preset chosen again).
 */
export function periodKey(period: Period): string {
  if (period.kind === "recent") return period.range;
  return `${period.from}..${period.kind === "dates" ? period.to : ""}`;
}

/** The period of a {@link periodKey}. */
export function periodOfKey(key: string): Period {
  if (isRange(key)) return { kind: "recent", range: key };
  const [from = "", to = ""] = key.split("..");
  return to === "" ? { kind: "since", from } : between(from, to);
}

export function samePeriod(a: Period, b: Period): boolean {
  return periodKey(a) === periodKey(b);
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

const MONTH_FORMAT = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" });

/** "September 2026" for "2026-09". */
export function formatMonth(month: string): string {
  return MONTH_FORMAT.format(dayDate(`${month}-01`));
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

/**
 * Days a period could not load, as its notice names them: "25 Sept 2026", "24 Sept 2026 and
 * 25 Sept 2026", past two their count and span, "12 days in 1 – 30 Sept 2026".
 */
export function formatMissingDays(days: readonly string[]): string {
  const sorted = [...days].sort();
  if (sorted.length > 2) {
    return `${sorted.length} days in ${formatDays(sorted[0] ?? "", sorted.at(-1) ?? "")}`;
  }
  return sorted.map((day) => DAY_FORMAT.format(dayDate(day))).join(" and ");
}

/**
 * The day an arrow key moves the calendar's focus to (UX-14): `step` days away (±1 a day,
 * ±7 a week), past the days that cannot be picked (no announcement); `null` beyond the
 * days stored.
 */
export function stepDay(
  from: string,
  step: number,
  canPick: (day: string) => boolean,
  bounds: { earliest: string; latest: string },
): string | null {
  if (step === 0) return null;
  const date = dayDate(from);
  for (;;) {
    date.setDate(date.getDate() + step);
    const day = isoDay(date);
    if (day < bounds.earliest || day > bounds.latest) return null;
    if (canPick(day)) return day;
  }
}
