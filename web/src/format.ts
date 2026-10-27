import { LOCALE } from "./locale";
import type { ArchiveSummary, DaySummary, TopRecentSummary } from "./types";

/** Format an ISO date or timestamp as a short, locale-aware day, e.g. "25 Sept 2026". */
export function formatDay(iso: string): string {
  const date = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return date.toLocaleDateString(LOCALE, { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Whether a paper is dated by its month (META-5): one announced before the oldest day file
 * comes from arXiv's catalog (the archive, and the most cited papers of the last 12 months
 * that no day file holds), which dates it by its first version, or the 1st of its
 * identifier's month, rather than by the day arXiv announced it.
 */
export function datedByMonth(announced: string, oldestDay: string | undefined): boolean {
  return oldestDay !== undefined && announced < oldestDay;
}

/** When a paper was announced: its day ("25 Sept 2026"), or its month ("Mar 2021") alone. */
export function formatAnnounced(announced: string, oldestDay: string | undefined): string {
  if (!datedByMonth(announced, oldestDay)) return formatDay(announced);
  return new Date(`${announced}T00:00:00`).toLocaleDateString(LOCALE, {
    month: "short",
    year: "numeric",
  });
}

/** What a date shown by its month alone means, for its tooltip. */
export const DATED_BY_MONTH =
  "Dated by month: arXiv's catalog, where this paper comes from, does not say on which day it was announced";

/**
 * A count and its noun, singular for one: "1 paper", "10,000 papers" (with the reader's
 * thousands separator), "2 people" with `plural`.
 */
export function countOf(count: number, noun: string, plural = `${noun}s`): string {
  return `${count.toLocaleString(LOCALE)} ${count === 1 ? noun : plural}`;
}

/**
 * What a view loads, as the store index counts it: the days of a period, archive years, or
 * the most cited papers of the last 12 months.
 */
export type Loading =
  | { days: readonly DaySummary[] }
  | { years: readonly ArchiveSummary[] }
  | { recent: TopRecentSummary };

/**
 * What a view says while it loads (UX-6), from the counts of the store index: "Loading
 * 3,646 papers of 5 days…" ("of 25 Sept 2026" for one day), "Loading 3,407 highly cited
 * papers of 2024…", "Loading 22,169 highly cited papers of 16 years…": the archive's count
 * is what is downloaded, before the budget keeps the best ranked. "Loading 1,000 highly
 * cited papers of the last 12 months…". "Loading papers…" while there is nothing to count:
 * before the index arrives, or for no day or year.
 */
export function loadingLine(loading: Loading): string {
  if ("recent" in loading) {
    return `Loading ${countOf(loading.recent.count, "highly cited paper")} of the last 12 months…`;
  }
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
 * What a stored paper weighs in its file as the site serves it, compressed (PROD-21): cs.CV's
 * 30,842 took 21 MB on 2026-10-27, day files, top-recent and archive together.
 */
const STORED_MB_PER_PAPER = 0.00068;

/**
 * What a search of every stored paper reads (PROD-21), in its ⓘ: the days kept, the most
 * cited papers of the last 12 months, the archive's years, and what its first search
 * downloads; the browser keeps the files, asking only whether they changed after ten
 * minutes, as Pages lets it.
 */
export function storeNote(store: {
  /** The oldest day file. */
  oldestDay: string | undefined;
  /** The archive's first year. */
  since: number | undefined;
  /** Whether the most cited papers of the last 12 months are kept apart. */
  recent: boolean;
  /** The papers of the store's files, as the index counts them. */
  papers: number;
}): string {
  const parts = [
    ...(store.oldestDay ? [`each day since ${formatDay(store.oldestDay)}`] : []),
    ...(store.recent ? ["the most cited papers of the last 12 months"] : []),
    ...(store.since === undefined
      ? []
      : [`the older papers the archive keeps for their citations, since ${store.since}`]),
  ];
  const listed =
    parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}` : parts.join("");
  const size = Math.max(1, Math.round(store.papers * STORED_MB_PER_PAPER));
  return (
    `Every paper the site stores${listed ? `: ${listed}` : ""}. Each search reads them all ` +
    `in your browser: about ${size} MB to download the first time, little after.`
  );
}

/** What screen readers hear of a search of every stored paper until it ends (UX-51). */
export const SEARCHING_STORE = "Searching every stored paper…";

/**
 * What a search of every stored paper says while it runs (UX-51): the share of the stored
 * papers it read, and how many passed the test, which the index ranks next, some not
 * matching ("Searching… 42% · 1,204 papers may match", a phone's line); then "Ranking 1,204
 * papers…".
 */
export function storeSearchLine(
  scan: { read: number; found: number } | { ranking: number },
  stored: number,
): string {
  if ("ranking" in scan) return `Ranking ${countOf(scan.ranking, "paper")}…`;
  const percent = Math.floor((100 * Math.min(scan.read, stored)) / Math.max(1, stored));
  const found = scan.found > 0 ? ` · ${countOf(scan.found, "paper")} may match` : "";
  return `Searching… ${percent}%${found}`;
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
  const known = `Affiliations known for ${affiliated.toLocaleString(LOCALE)} of ${countOf(total, noun)}`;
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
  return new Date(`${iso}T00:00:00`).toLocaleDateString(LOCALE, {
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
  const age = citationsAge(asOf, today);
  return staleCitations(asOf, today) ? `${note} (${age} days ago: they may be out of date)` : note;
}

function citationsAge(asOf: string, today: Date): number {
  return Math.floor((today.getTime() - new Date(asOf).getTime()) / DAY_MS);
}

/** Whether counts of this date are old enough for a list to say so above its papers. */
export function staleCitations(asOf: string, today: Date = new Date()): boolean {
  return citationsAge(asOf, today) > STALE_CITATIONS_DAYS;
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
    text: `+${gain.toLocaleString(LOCALE)} ${when}`,
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

const MONTH_FORMAT = new Intl.DateTimeFormat(LOCALE, { month: "short" });

/**
 * The label of an archive year: "2025, Jan–Oct" for the youngest year, which only holds
 * papers older than 12 months on `asOf`, else the year alone.
 */
export function archiveYearLabel(year: number, asOf: Date): string {
  const cutoff = new Date(asOf.getFullYear() - 1, asOf.getMonth(), 1);
  if (year !== cutoff.getFullYear() || cutoff.getMonth() === 11) return String(year);
  return `${year}, ${MONTH_FORMAT.format(new Date(year, 0, 1))}–${MONTH_FORMAT.format(cutoff)}`;
}
