/**
 * Atom feeds, which the build writes (`tooling/feeds.ts`, §17.1 #6): for each institution of
 * the stored days and each major venue, its latest papers, so that a feed reader follows a
 * lab or a conference without a server or an account. The site links the feed of the
 * institution or venue a list is filtered on.
 */
import type { SearchFilters } from "./search";
import { searchKey } from "./text";
import { ANY_VENUE, familyOf, MAJOR_VENUES, venueFamily } from "./venues";

/** Days of papers a feed holds, back from the newest day stored. */
export const FEED_DAYS = 60;

/**
 * The file name of a name's feed: its search key, hyphenated ("massachusetts-institute-of-
 * technology"), so that every spelling the graph counts as one institution has one feed.
 */
export function feedSlug(name: string): string {
  return searchKey(name).replaceAll(" ", "-");
}

/** Path of an institution's feed, under the site; `null` for a name without letters. */
export function institutionFeedPath(category: string, institution: string): string | null {
  const slug = feedSlug(institution);
  return slug ? `feeds/${category}/institutions/${slug}.xml` : null;
}

/** Path of a major venue's feed (all its editions, not its workshops), under the site. */
export function venueFeedPath(category: string, venue: (typeof MAJOR_VENUES)[number]): string {
  return `feeds/${category}/venues/${feedSlug(venue)}.xml`;
}

/** The major venue a venue filter is about: "CVPR 2026" and "CVPR*" are CVPR. */
function majorVenueOf(filter: string): (typeof MAJOR_VENUES)[number] | null {
  if (filter === ANY_VENUE) return null;
  const family = familyOf(filter) ?? venueFamily(filter);
  return MAJOR_VENUES.find((venue) => venue === family) ?? null;
}

export interface FeedLink {
  path: string;
  /** What it follows: "MIT", "CVPR". */
  name: string;
  kind: "institution" | "venue";
}

/**
 * The feed of what the papers are filtered on, if there is one: an institution as clicked
 * (an exact filter, the name the feeds use) that has a feed, else a major venue. The build
 * writes the feeds of the day files' institutions only: `hasFeed` says whether the papers
 * loaded name it, so that an institution of the archive alone ("OpenAI") links no 404.
 */
export function feedOf(
  category: string,
  filters: SearchFilters,
  hasFeed: (institution: string) => boolean,
): FeedLink | null {
  const { affiliation, venue } = filters;
  if (affiliation?.exact && hasFeed(affiliation.text)) {
    const path = institutionFeedPath(category, affiliation.text);
    if (path !== null) return { path, name: affiliation.text, kind: "institution" };
  }
  const major = venue === null ? null : majorVenueOf(venue);
  return major === null
    ? null
    : { path: venueFeedPath(category, major), name: major, kind: "venue" };
}
