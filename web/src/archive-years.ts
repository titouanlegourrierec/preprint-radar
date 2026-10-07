/**
 * The years of the archive a view shows: one, a range, or all of them (`?year=2017`,
 * `?year=2019-2021`, `?year=all`). Over {@link PAPER_BUDGET} papers, the view keeps the
 * best ranked by the archive's own score, citations per year of age, and says how many it
 * leaves out: all years hold about 22,000 papers, 300 MB once indexed.
 */
import { archiveYearLabel } from "./format";
import { PAPER_BUDGET } from "./period";
import type { ArchiveSummary, Paper } from "./types";

/** First and last year, both included; both `null` for all years, however many come. */
export interface YearRange {
  from: number | null;
  to: number | null;
}

export const ALL_YEARS: YearRange = { from: null, to: null };

export function oneYear(year: number): YearRange {
  return { from: year, to: year };
}

const RANGE_RE = /^(\d{4})(?:-(\d{4}))?$/;

/** A range from the URL: "2017", "2019-2021" (either order) or "all"; `null` otherwise. */
export function parseYears(text: string | null): YearRange | null {
  if (text === "all") return ALL_YEARS;
  const match = RANGE_RE.exec(text ?? "");
  if (!match) return null;
  const first = Number(match[1]);
  const second = match[2] === undefined ? first : Number(match[2]);
  return { from: Math.min(first, second), to: Math.max(first, second) };
}

/** A range for the URL, the inverse of {@link parseYears}. */
export function formatYears(range: YearRange): string {
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
 * The range as shown: what the URL asks, else the latest year; a range without any year
 * of the archive is the latest year too. `null` before the first archive.
 */
export function shownYears(
  requested: YearRange | null,
  years: readonly ArchiveSummary[],
): YearRange | null {
  const latest = years[0]?.year;
  if (latest === undefined) return null;
  return requested !== null && yearsIn(requested, years).length > 0 ? requested : oneYear(latest);
}

/** "2017", "2019–2021", "all years", for the views' sentences. */
export function yearsLabel(range: YearRange, years: readonly ArchiveSummary[]): string {
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
 * when they fit. Unknown counts rank last.
 */
export function bestRanked(
  papers: readonly Paper[],
  counts: ReadonlyMap<string, number>,
  asOf: Date,
  budget: number = PAPER_BUDGET,
): Paper[] {
  if (papers.length <= budget) return [...papers];
  const score = new Map(
    papers.map((paper) => [paper, citationRate(counts.get(paper.arxiv_id), paper.announced, asOf)]),
  );
  return [...papers].sort((a, b) => (score.get(b) ?? 0) - (score.get(a) ?? 0)).slice(0, budget);
}

/**
 * When the papers of a range were first published, for the view's count: "in 2024" ("in
 * 2025, Jan–Oct" for the youngest year), "from 2019 to 2021".
 */
export function publishedIn(
  range: YearRange,
  years: readonly ArchiveSummary[],
  asOf: Date | undefined,
): string {
  const shown = yearsIn(range, years);
  const first = shown.at(-1)?.year;
  const last = shown[0]?.year;
  if (first === undefined || last === undefined) return "";
  if (first === last) return `in ${asOf ? archiveYearLabel(first, asOf) : first}`;
  return `from ${first} to ${last}`;
}
