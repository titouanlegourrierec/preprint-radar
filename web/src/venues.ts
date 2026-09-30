import type { FacetCount } from "./search";
import { fold } from "./text";

/** Venues pinned at the top of the venue filter, in this order. */
export const MAJOR_VENUES = ["NeurIPS", "ICML", "ICLR", "CVPR", "ICCV", "ECCV", "MICCAI"] as const;

/** Position of a venue among the major ones ("NeurIPS 2026 Workshop" counts as NeurIPS). */
function majorRank(venue: string): number {
  const rank = MAJOR_VENUES.findIndex((name) => venue === name || venue.startsWith(`${name} `));
  return rank === -1 ? MAJOR_VENUES.length : rank;
}

/** Whether the venue is a major one ("NeurIPS 2026 Workshop" counts as NeurIPS). */
export function isMajorVenue(venue: string): boolean {
  return majorRank(venue) < MAJOR_VENUES.length;
}

/** Order venues for the filter: major venues first, then the rest alphabetically. */
export function sortVenues(venues: readonly FacetCount[]): FacetCount[] {
  return [...venues].sort(
    (a, b) => majorRank(a.value) - majorRank(b.value) || fold(a.value).localeCompare(fold(b.value)),
  );
}
