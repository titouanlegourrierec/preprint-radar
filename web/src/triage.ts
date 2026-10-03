/**
 * Daily triage, kept in this browser: the papers marked seen, and the newest day shown at
 * the previous visit ("since last visit"). Never in the URL, so shared links stay neutral.
 */
import type { DaySummary } from "./types";

/** Months of identifiers kept in the seen set; older papers have left the recent days. */
export const SEEN_MONTHS = 3;

const seenKey = (category: string) => `preprint-radar:seen:${category}`;
const lastVisitKey = (category: string) => `preprint-radar:last-visit:${category}`;
const sessionKey = (category: string) => `preprint-radar:previous-visit:${category}`;

// New-style identifiers start with the year and month of their first version: "2609.30234".
const NEW_STYLE_ID_RE = /^(\d{2})(\d{2})\.\d{4,5}$/;

/**
 * The identifiers of papers first submitted in the last {@link SEEN_MONTHS} months of
 * `today`, so that the seen set does not grow forever (about 130 papers a day).
 */
export function pruneSeen(ids: Iterable<string>, today: Date): string[] {
  const cutoff = new Date(today.getFullYear(), today.getMonth() - SEEN_MONTHS, 1);
  const oldest = (cutoff.getFullYear() % 100) * 100 + cutoff.getMonth() + 1;
  return [...ids].filter((id) => {
    const match = NEW_STYLE_ID_RE.exec(id);
    return match !== null && Number(match[1]) * 100 + Number(match[2]) >= oldest;
  });
}

/** The papers of `category` marked seen in this browser. */
export function loadSeen(category: string): Set<string> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(seenKey(category)) ?? "[]");
    return new Set(Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

export function saveSeen(category: string, ids: ReadonlySet<string>, today = new Date()): void {
  try {
    localStorage.setItem(seenKey(category), JSON.stringify(pruneSeen(ids, today)));
  } catch {
    // Storage may be full or disabled (private browsing); the marks then last for the session.
  }
}

/**
 * The newest announcement day shown at the previous visit, and remember today's for the
 * next one. A visit is a browser session: reloading the page does not make "since last
 * visit" empty.
 *
 * @param newestDay The newest day stored now.
 * @returns `null` on a first visit, or when storage is unavailable.
 */
export function previousVisit(category: string, newestDay: string): string | null {
  try {
    const kept = sessionStorage.getItem(sessionKey(category));
    if (kept !== null) return kept || null;
    const previous = localStorage.getItem(lastVisitKey(category));
    sessionStorage.setItem(sessionKey(category), previous ?? "");
    localStorage.setItem(lastVisitKey(category), newestDay);
    return previous;
  } catch {
    return null;
  }
}

/** The days announced after the previous visit, and their papers. */
export interface NewDays {
  from: string;
  to: string;
  papers: number;
}

/**
 * The stored days newer than `previous` (most recent first, as in the index), or `null`
 * when there are none or no previous visit.
 */
export function newSince(days: readonly DaySummary[], previous: string | null): NewDays | null {
  if (previous === null) return null;
  const newer = days.filter((day) => day.date > previous);
  const [last, first] = [newer[0], newer.at(-1)];
  if (last === undefined || first === undefined) return null;
  return {
    from: first.date,
    to: last.date,
    papers: newer.reduce((total, day) => total + day.count, 0),
  };
}
