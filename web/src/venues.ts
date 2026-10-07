import type { FacetCount } from "./search";
import { fold } from "./text";
import type { Paper } from "./types";

/** Venues pinned at the top of the venue filter, in this order. */
export const MAJOR_VENUES = ["NeurIPS", "ICML", "ICLR", "CVPR", "ICCV", "ECCV", "MICCAI"] as const;

/** Venue filter value for papers accepted anywhere. */
export const ANY_VENUE = "*";

// The year of an edition, as the pipeline writes it ("CVPR 2026", "CVPR 2026 Workshop"),
// for the venues of its table and Semantic Scholar's alike (`venue.py`).
const EDITION_YEAR_RE = / (?:19|20)\d{2}(?= Workshop$|$)/;

/**
 * A venue without its year (SRCH-15): "CVPR 2026" is CVPR, "CVPR 2026 Workshop" is CVPR
 * Workshop, a family of its own, since its papers are not the conference's.
 */
export function venueFamily(venue: string): string {
  return venue.replace(EDITION_YEAR_RE, "");
}

/** The filter value of a family, every edition of it: "CVPR*". */
export function familyValue(family: string): string {
  return `${family}*`;
}

/** The family a filter value stands for, or `null` for one venue or {@link ANY_VENUE}. */
export function familyOf(value: string): string | null {
  return value.length > 1 && value.endsWith("*") ? value.slice(0, -1) : null;
}

/** Whether a paper's venue passes the venue filter: any venue, a family or one venue. */
export function matchesVenue(venue: string | null | undefined, filter: string): boolean {
  if (!venue) return false;
  if (filter === ANY_VENUE) return true;
  const family = familyOf(filter);
  return family === null ? venue === filter : venueFamily(venue) === family;
}

/** How the filter names a value: "any venue", "CVPR, any year", "ECCV 2026". */
export function venueLabel(value: string): string {
  if (value === ANY_VENUE) return "any venue";
  const family = familyOf(value);
  return family === null ? value : `${family}, any year`;
}

/**
 * The venue filter's values among the papers, the most frequent `limit`, with their
 * papers: each venue, and each family of more than one edition ("CVPR*" when "CVPR 2025"
 * and "CVPR 2026" are there), counted on the papers so that a cut edition still counts;
 * and first, {@link ANY_VENUE} with every paper accepted somewhere, which the cut editions
 * would undercount.
 */
export function venueFacets(papers: Iterable<Paper>, limit: number): FacetCount[] {
  let accepted = 0;
  const editions = new Map<string, number>();
  const families = new Map<string, { count: number; editions: Set<string> }>();
  for (const { venue } of papers) {
    if (!venue) continue;
    accepted += 1;
    editions.set(venue, (editions.get(venue) ?? 0) + 1);
    const family = venueFamily(venue);
    const entry = families.get(family) ?? { count: 0, editions: new Set<string>() };
    entry.count += 1;
    entry.editions.add(venue);
    families.set(family, entry);
  }
  const listed = [
    ...[...editions].map(([value, count]) => ({ value, count })),
    ...[...families]
      .filter(([, entry]) => entry.editions.size > 1)
      .map(([family, entry]) => ({ value: familyValue(family), count: entry.count })),
  ]
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
    .slice(0, limit);
  return [{ value: ANY_VENUE, count: accepted }, ...listed];
}

/**
 * Position of a venue or family among the major ones ("NeurIPS 2026 Workshop" and
 * "NeurIPS*" count as NeurIPS).
 */
function majorRank(value: string): number {
  const venue = familyOf(value) ?? value;
  const rank = MAJOR_VENUES.findIndex((name) => venue === name || venue.startsWith(`${name} `));
  return rank === -1 ? MAJOR_VENUES.length : rank;
}

/** Whether the venue is a major one ("NeurIPS 2026 Workshop" counts as NeurIPS). */
export function isMajorVenue(venue: string): boolean {
  return majorRank(venue) < MAJOR_VENUES.length;
}

/**
 * Order venues for the filter: major venues first, then the rest alphabetically, each
 * family before its editions ("CVPR, any year", "CVPR 2025", "CVPR 2026", then CVPR
 * Workshop's).
 */
export function sortVenues(venues: readonly FacetCount[]): FacetCount[] {
  const family = (value: string) => familyOf(value) ?? venueFamily(value);
  return [...venues].sort(
    (a, b) =>
      majorRank(a.value) - majorRank(b.value) ||
      fold(family(a.value)).localeCompare(fold(family(b.value))) ||
      Number(familyOf(b.value) !== null) - Number(familyOf(a.value) !== null) ||
      fold(a.value).localeCompare(fold(b.value)),
  );
}
