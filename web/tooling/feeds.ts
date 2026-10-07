import { FEED_DAYS, institutionFeedPath, venueFeedPath } from "../src/feeds";
import { namedInstitutions } from "../src/institutions";
import { searchKey } from "../src/text";
import type { Paper, ScholarFile, StoreIndex } from "../src/types";
import { MAJOR_VENUES, venueFamily } from "../src/venues";
import type { ReadJson } from "./citation-shards";
import { mergeScholar, type StoredPaper } from "./scholar";

/** Entries of an institution's feed: a week of a large lab's papers. */
export const INSTITUTION_ENTRIES = 30;
/** Entries of a venue's feed, which can take dozens of papers a day around its decisions. */
export const VENUE_ENTRIES = 100;
/** Authors an entry names, then "and N more": consortium papers list hundreds. */
const ENTRY_AUTHORS = 10;
const DAY_MS = 86_400_000;

/**
 * Whether XML 1.0 takes a character, escaped or not: not control characters (but tab and
 * line breaks), halves of surrogate pairs, or U+FFFE and U+FFFF.
 */
function isXmlChar(char: string): boolean {
  const code = char.codePointAt(0) ?? 0;
  return (
    code === 0x9 ||
    code === 0xa ||
    code === 0xd ||
    (code >= 0x20 && code < 0xd800) ||
    (code >= 0xe000 && code <= 0xfffd) ||
    code >= 0x10000
  );
}

function xml(text: string): string {
  return [...text]
    .filter(isXmlChar)
    .join("")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** A day as an Atom date: arXiv announces at midnight Eastern time, which the day is enough for. */
function atomDay(day: string): string {
  return `${day}T00:00:00Z`;
}

function entry(paper: Paper): string {
  const authors = paper.authors.slice(0, ENTRY_AUTHORS);
  const more = paper.authors.length - authors.length;
  return [
    "  <entry>",
    `    <id>${xml(paper.abs_url)}</id>`,
    `    <title>${xml(paper.title)}</title>`,
    `    <link rel="alternate" type="text/html" href="${xml(paper.abs_url)}"/>`,
    `    <published>${atomDay(paper.announced)}</published>`,
    `    <updated>${atomDay(paper.announced)}</updated>`,
    ...authors.map((author) => `    <author><name>${xml(author)}</name></author>`),
    ...(more > 0 ? [`    <author><name>and ${more} more</name></author>`] : []),
    ...(paper.venue ? [`    <category term="${xml(paper.venue)}"/>`] : []),
    ...(paper.abstract ? [`    <summary type="text">${xml(paper.abstract)}</summary>`] : []),
    "  </entry>",
  ].join("\n");
}

interface Feed {
  /** Path under the site, which its `self` link and id take. */
  path: string;
  title: string;
  subtitle: string;
  /** The site's view of the same papers, as a query string. */
  view: string;
  papers: Paper[];
  /** Its date when it has no entry: the newest day stored. */
  newestDay: string;
}

/**
 * An Atom feed. Its id is its address on the site when the build knows it (`siteUrl`, set
 * by the deploy workflow), so that it stays the same across builds; else a URN, for local
 * builds, whose feeds nobody follows.
 */
export function atomFeed(feed: Feed, siteUrl: string | null): string {
  const site = siteUrl === null ? null : siteUrl.replace(/\/?$/, "/");
  const id = site === null ? `urn:preprint-radar:${feed.path}` : `${site}${feed.path}`;
  const updated = feed.papers[0]?.announced ?? feed.newestDay;
  return [
    '<?xml version="1.0" encoding="utf-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom">',
    `  <id>${xml(id)}</id>`,
    `  <title>${xml(feed.title)}</title>`,
    `  <subtitle>${xml(feed.subtitle)}</subtitle>`,
    `  <updated>${atomDay(updated)}</updated>`,
    ...(site === null
      ? []
      : [
          `  <link rel="self" type="application/atom+xml" href="${xml(`${site}${feed.path}`)}"/>`,
          `  <link rel="alternate" type="text/html" href="${xml(`${site}${feed.view}`)}"/>`,
        ]),
    "  <generator>Preprint Radar</generator>",
    ...feed.papers.map(entry),
    "</feed>",
    "",
  ].join("\n");
}

/** An institution of the day files: how its papers write it, and its recent papers. */
interface Institution {
  spellings: Map<string, number>;
  papers: Paper[];
}

/** Newest first, as the list shows them. */
function newestFirst(a: Paper, b: Paper): number {
  return b.announced.localeCompare(a.announced) || b.arxiv_id.localeCompare(a.arxiv_id);
}

/** The most frequent of a name's spellings, the one its feed is titled with. */
function usualName(spellings: Map<string, number>): string {
  return [...spellings].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? "";
}

/**
 * The feeds of a store, as XML text by path under the site (§17.1 #6). Each category has
 * one for every institution its day files name, with its papers of the last
 * {@link FEED_DAYS} days (an institution of the store keeps its feed, empty once it has
 * published nothing for that long), and one for each major venue, all its editions. The
 * records are the site's: a venue Semantic Scholar names counts.
 */
export function feedFiles(read: ReadJson, siteUrl: string | null): Map<string, string> {
  const files = new Map<string, string>();
  const index = read("index.json") as StoreIndex | null;
  if (index === null) return files;
  for (const [category, days] of Object.entries(index.categories)) {
    const newestDay = days
      .map(({ date }) => date)
      .sort()
      .at(-1);
    if (newestDay === undefined) continue;
    const since = new Date(new Date(atomDay(newestDay)).getTime() - FEED_DAYS * DAY_MS)
      .toISOString()
      .slice(0, 10);
    const scholar = read(`${category}/scholar.json`) as ScholarFile | null;
    const institutions = new Map<string, Institution>();
    const recent: Paper[] = [];
    for (const { date } of days) {
      const papers = (read(`${category}/${date}.json`) as { papers: Paper[] }).papers;
      if (scholar !== null) mergeScholar(papers as StoredPaper[], scholar);
      for (const paper of papers) {
        const isRecent = paper.announced > since;
        if (isRecent) recent.push(paper);
        // Once per institution, however many of its affiliations name it.
        const named = new Map(namedInstitutions(paper).map((name) => [searchKey(name), name]));
        for (const [key, name] of named) {
          const entry: Institution = institutions.get(key) ?? { spellings: new Map(), papers: [] };
          entry.spellings.set(name, (entry.spellings.get(name) ?? 0) + 1);
          if (isRecent) entry.papers.push(paper);
          institutions.set(key, entry);
        }
      }
    }
    for (const { spellings, papers } of institutions.values()) {
      const name = usualName(spellings);
      const path = institutionFeedPath(category, name);
      if (path === null) continue;
      const feed = {
        path,
        title: `${name}: ${category} preprints`,
        subtitle: `The ${category} papers announced on arXiv in the last ${FEED_DAYS} days with an author at ${name}, from Preprint Radar.`,
        view: `?${new URLSearchParams({ cat: category, at: name })}`,
        papers: papers.sort(newestFirst).slice(0, INSTITUTION_ENTRIES),
        newestDay,
      };
      files.set(path, atomFeed(feed, siteUrl));
    }
    for (const venue of MAJOR_VENUES) {
      const papers = recent.filter((paper) => paper.venue && venueFamily(paper.venue) === venue);
      const feed = {
        path: venueFeedPath(category, venue),
        title: `${venue}: ${category} preprints`,
        subtitle: `The ${category} papers announced on arXiv in the last ${FEED_DAYS} days that say they were accepted at ${venue}, any year, from Preprint Radar.`,
        view: `?${new URLSearchParams({ cat: category, venue: `${venue}*` })}`,
        papers: papers.sort(newestFirst).slice(0, VENUE_ENTRIES),
        newestDay,
      };
      files.set(feed.path, atomFeed(feed, siteUrl));
    }
  }
  return files;
}
