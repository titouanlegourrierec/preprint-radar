/** Format an ISO date or timestamp as a short, locale-aware day, e.g. "25 Sept 2026". */
export function formatDay(iso: string): string {
  const date = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
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
