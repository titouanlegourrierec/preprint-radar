import type { ArchiveSummary, DaySummary } from "./types";

/** Format an ISO date or timestamp as a short, locale-aware day, e.g. "25 Sept 2026". */
export function formatDay(iso: string): string {
  const date = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/**
 * A count and its noun, singular for one: "1 paper", "10,000 papers" (with the reader's
 * thousands separator), "2 people" with `plural`.
 */
export function countOf(count: number, noun: string, plural = `${noun}s`): string {
  return `${count.toLocaleString()} ${count === 1 ? noun : plural}`;
}

/** What a view loads, as the store index counts it: the days of a period, or archive years. */
export type Loading = { days: readonly DaySummary[] } | { years: readonly ArchiveSummary[] };

/**
 * What a view says while it loads (UX-6), from the counts of the store index: "Loading
 * 3,646 papers of 5 days…" ("of 25 Sept 2026" for one day), "Loading 3,407 highly cited
 * papers of 2024…", "Loading 22,169 highly cited papers of 16 years…": the archive's count
 * is what is downloaded, before the budget keeps the best ranked. "Loading papers…" while
 * there is nothing to count: before the index arrives, or for no day or year.
 */
export function loadingLine(loading: Loading): string {
  const summaries: readonly { count: number }[] = "days" in loading ? loading.days : loading.years;
  if (summaries.length === 0) return "Loading papers…";
  const total = summaries.reduce((sum, { count }) => sum + count, 0);
  if ("days" in loading) {
    const day = loading.days.length === 1 ? loading.days[0] : undefined;
    const of = day ? formatDay(day.date) : countOf(loading.days.length, "day");
    return `Loading ${countOf(total, "paper")} of ${of}…`;
  }
  const year = loading.years.length === 1 ? loading.years[0] : undefined;
  const of = year ? String(year.year) : countOf(loading.years.length, "year");
  return `Loading ${countOf(total, "highly cited paper")} of ${of}…`;
}

/**
 * What "Hide seen" leaves out of the list, for its count ("· 12 seen papers hidden") and for
 * an empty list, where it is the reason: "All 12 papers here are marked seen."
 */
export function seenHidden(count: number): { count: string; empty: string } {
  return {
    count: `${countOf(count, "seen paper")} hidden`,
    empty:
      count === 1
        ? "The only paper here is marked seen."
        : `All ${countOf(count, "paper")} here are marked seen.`,
  };
}

/**
 * How many papers have known affiliations, for the notes of Rankings and the graph (PROD-16):
 * "Affiliations known for 331 of 2,018 papers (16%)". Below half, as the share reads, it
 * adds that the others count for no institution, so that a ranking on a minority of papers
 * is not read as the whole field (recent archive years are still being filled in, but older
 * ones and narrow searches are not).
 */
export function affiliationCoverage(affiliated: number, total: number, noun = "paper"): string {
  const known = `Affiliations known for ${affiliated.toLocaleString()} of ${countOf(total, noun)}`;
  if (total === 0) return known;
  const percent = Math.round((affiliated / total) * 100);
  const share = `${known} (${percentLabel(percent, affiliated, total)})`;
  return percent < 50 ? `${share}: the others count for no institution` : share;
}

/** A share in whole percent, never 0% for a few nor 100% for nearly all: "16%", "<1%". */
function percentLabel(percent: number, part: number, whole: number): string {
  if (percent === 0 && part > 0) return "<1%";
  if (percent === 100 && part < whole) return ">99%";
  return `${percent}%`;
}

/** Subject code from its full name, e.g. "Robotics (cs.RO)" -> "cs.RO". */
export function subjectCode(subject: string): string {
  return /\(([^()]+)\)\s*$/.exec(subject)?.[1] ?? subject;
}

/** Format an ISO date as a short day with its weekday, e.g. "Tue 8 Sept". */
export function formatShortDay(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/** Counts refreshed longer ago are stale: weekly runs failed (`STALE_CITATIONS_DAYS` in config.py). */
export const STALE_CITATIONS_DAYS = 14;

const DAY_MS = 86_400_000;

/** The note on citation counts: their source and date, and a warning once they are stale. */
export function citationsNote(source: string, asOf: string, today: Date = new Date()): string {
  const note = `Citations on ${source}, as of ${formatDay(asOf)}`;
  const age = Math.floor((today.getTime() - new Date(asOf).getTime()) / DAY_MS);
  return age > STALE_CITATIONS_DAYS ? `${note} (${age} days ago: they may be out of date)` : note;
}

/** Days of a weekly refresh, and a day of slack for a run that started late. */
const WEEK_DAYS = 8;

/**
 * A paper's citation gain between two weekly refreshes (CIT-9), as its card shows it ("+12
 * this week", or "+12 since 4 Oct" when the refreshes were further apart), and its tooltip.
 */
export function gainLabel(
  gain: number,
  span: { since: string; to: string },
  source: string | null,
): { text: string; title: string } {
  const days = Math.round((new Date(span.to).getTime() - new Date(span.since).getTime()) / DAY_MS);
  const when = days <= WEEK_DAYS ? "this week" : `since ${formatDay(span.since)}`;
  const citations = countOf(gain, "new citation");
  return {
    text: `+${gain.toLocaleString()} ${when}`,
    title: `${citations}${source ? ` on ${source}` : ""} between ${formatDay(span.since)} and ${formatDay(span.to)}`,
  };
}

// The arXiv name of each category the store may hold; another shows as its code alone.
const CATEGORY_NAMES: Readonly<Record<string, string>> = {
  "cs.CV": "Computer Vision and Pattern Recognition",
  "cs.LG": "Machine Learning",
  "cs.CL": "Computation and Language",
  "cs.RO": "Robotics",
  "cs.AI": "Artificial Intelligence",
  "cs.GR": "Graphics",
  "eess.IV": "Image and Video Processing",
};

/** "cs.CV (Computer Vision and Pattern Recognition)", or the code of an unknown category. */
export function categoryName(category: string): string {
  const name = CATEGORY_NAMES[category];
  return name ? `${category} (${name})` : category;
}

// A new-style arXiv identifier ("1906.07927", since April 2007): the year and month of its
// first version, then its number.
const NEW_STYLE_ID_RE = /^(\d{2})(\d{2})\.\d{4,5}$/;

/** Months between a paper's first version and its announcement past which its card says so. */
const OLD_VERSION_MONTHS = 12;

/**
 * The year of a paper's first version when it came 12 months or more before the day it was
 * announced in the category (PROD-14), as an old paper cross-listed lately is: its card
 * says "first version 2019". Months are compared, the identifier holding no day. `null`
 * for a younger paper, and for an old-style identifier ("cs/0601001"), which is not read.
 */
export function firstVersionYear(arxivId: string, announced: string): number | null {
  const id = NEW_STYLE_ID_RE.exec(arxivId);
  const day = /^(\d{4})-(\d{2})-\d{2}$/.exec(announced);
  if (!(id && day)) return null;
  const year = 2000 + Number(id[1]);
  const month = Number(id[2]);
  if (month < 1 || month > 12) return null;
  const months = (Number(day[1]) - year) * 12 + (Number(day[2]) - month);
  return months >= OLD_VERSION_MONTHS ? year : null;
}

/** Whole days from an ISO day to `today`. */
export function daysSince(iso: string, today: Date = new Date()): number {
  return Math.floor((today.getTime() - new Date(`${iso}T00:00:00`).getTime()) / DAY_MS);
}

const MONTH_FORMAT = new Intl.DateTimeFormat(undefined, { month: "short" });

/**
 * The label of an archive year: "2025, Jan–Oct" for the youngest year, which only holds
 * papers older than 12 months on `asOf`, else the year alone.
 */
export function archiveYearLabel(year: number, asOf: Date): string {
  const cutoff = new Date(asOf.getFullYear() - 1, asOf.getMonth(), 1);
  if (year !== cutoff.getFullYear() || cutoff.getMonth() === 11) return String(year);
  return `${year}, ${MONTH_FORMAT.format(new Date(year, 0, 1))}–${MONTH_FORMAT.format(cutoff)}`;
}
