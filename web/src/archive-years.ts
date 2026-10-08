/**
 * The years of the archive a view shows: one, a range, or all of them (`?year=2017`,
 * `?year=2019-2021`, `?year=all`). Over {@link PAPER_BUDGET} papers, the view keeps the
 * best ranked by the archive's own score, citations per year of age, and says how many it
 * leaves out: all years hold about 22,000 papers, 300 MB once indexed. Or the most cited
 * papers of the last 12 months, which the archive keeps apart (`?year=last-12-months`,
 * PROD-11).
 */
import { archiveYearLabel, formatDay } from "./format";
import { PAPER_BUDGET } from "./period";
import type { ArchiveSummary, Paper, TopRecentSummary } from "./types";

/** First and last year, both included; both `null` for all years, however many come. */
export interface YearRange {
  from: number | null;
  to: number | null;
}

export const ALL_YEARS: YearRange = { from: null, to: null };

/** The most cited papers of the last 12 months, apart from the archive's years (PROD-11). */
export const LAST_12_MONTHS = "last-12-months" as const;

/** What the highly cited view shows: archive years, or the most cited papers of the last 12 months. */
export type ArchiveRange = YearRange | typeof LAST_12_MONTHS;

export function oneYear(year: number): YearRange {
  return { from: year, to: year };
}

const RANGE_RE = /^(\d{4})(?:-(\d{4}))?$/;

/**
 * A range from the URL: "2017", "2019-2021" (either order), "all" or "last-12-months";
 * `null` otherwise.
 */
export function parseYears(text: string | null): ArchiveRange | null {
  if (text === "all") return ALL_YEARS;
  if (text === LAST_12_MONTHS) return LAST_12_MONTHS;
  const match = RANGE_RE.exec(text ?? "");
  if (!match) return null;
  const first = Number(match[1]);
  const second = match[2] === undefined ? first : Number(match[2]);
  return { from: Math.min(first, second), to: Math.max(first, second) };
}

/** A range for the URL, the inverse of {@link parseYears}. */
export function formatYears(range: ArchiveRange): string {
  if (range === LAST_12_MONTHS) return range;
  if (range.from === null || range.to === null) return "all";
  return range.from === range.to ? String(range.from) : `${range.from}-${range.to}`;
}

/** The archive's years within the range, newest first, as the index lists them. */
export function yearsIn(range: YearRange, years: readonly ArchiveSummary[]): ArchiveSummary[] {
  return years.filter(
    ({ year }) =>
      (range.from === null || year >= range.from) && (range.to === null || year <= range.to),
  );
}

/**
 * The range as shown: what the URL asks, within the archive's years ("2005-2010" is 2010,
 * the first one, rather than a From select without its year), else the latest year; a
 * range without any year of the archive is the latest year too, and so are the last 12
 * months before the archive keeps them (`recent`). The last 12 months without any year;
 * `null` before the first archive.
 */
export function shownYears(
  requested: ArchiveRange | null,
  years: readonly ArchiveSummary[],
  recent?: TopRecentSummary,
): ArchiveRange | null {
  if (requested === LAST_12_MONTHS) {
    if (recent !== undefined) return LAST_12_MONTHS;
    requested = null;
  }
  const latest = years[0]?.year;
  if (latest === undefined) return recent === undefined ? null : LAST_12_MONTHS;
  if (requested === null || yearsIn(requested, years).length === 0) return oneYear(latest);
  if (requested.from === null || requested.to === null) return requested;
  const oldest = years.at(-1)?.year ?? latest;
  return { from: Math.max(requested.from, oldest), to: Math.min(requested.to, latest) };
}

/** "2017", "2019–2021", "all years", "the last 12 months", for the views' sentences. */
export function yearsLabel(range: ArchiveRange, years: readonly ArchiveSummary[]): string {
  if (range === LAST_12_MONTHS) return "the last 12 months";
  if (range.from === null || range.to === null) return "all years";
  const shown = yearsIn(range, years);
  const first = shown.at(-1)?.year;
  const last = shown[0]?.year;
  return first === last ? String(first) : `${first}–${last}`;
}

const DAYS_PER_YEAR = 365.25;
const DAY_MS = 86_400_000;

/**
 * Citations per year of age, counting at least one year: the archive's score
 * (`archive/selection.py`), which compares a 2015 paper and a 2024 one fairly.
 */
export function citationRate(citations: number | undefined, announced: string, asOf: Date): number {
  const age =
    (asOf.getTime() - new Date(`${announced}T00:00:00Z`).getTime()) / DAY_MS / DAYS_PER_YEAR;
  return (citations ?? 0) / Math.max(age, 1);
}

/**
 * The papers within `budget`, the best ranked by {@link citationRate} first; all of them
 * when they fit. Unknown counts rank last, after those of none.
 */
export function bestRanked(
  papers: readonly Paper[],
  counts: ReadonlyMap<string, number>,
  asOf: Date,
  budget: number = PAPER_BUDGET,
): Paper[] {
  if (papers.length <= budget) return [...papers];
  const score = new Map(
    papers.map((paper) => {
      const count = counts.get(paper.arxiv_id);
      return [paper, count === undefined ? -1 : citationRate(count, paper.announced, asOf)];
    }),
  );
  return [...papers].sort((a, b) => (score.get(b) ?? 0) - (score.get(a) ?? 0)).slice(0, budget);
}

/**
 * When the papers of a range were first published, for the view's count: "in 2024" ("in
 * 2025, Jan–Oct" for the youngest year), "from 2019 to 2021", "since 1 Oct 2025" for the
 * last 12 months (`recent`, as the archive chose them).
 */
export function publishedIn(
  range: ArchiveRange,
  years: readonly ArchiveSummary[],
  asOf: Date | undefined,
  recent?: TopRecentSummary,
): string {
  if (range === LAST_12_MONTHS) {
    return recent ? `since ${formatDay(recent.since)}` : "in the last 12 months";
  }
  const shown = yearsIn(range, years);
  const first = shown.at(-1)?.year;
  const last = shown[0]?.year;
  if (first === undefined || last === undefined) return "";
  if (first === last) return `in ${asOf ? archiveYearLabel(first, asOf) : first}`;
  return `from ${first} to ${last}`;
}
