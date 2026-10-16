import { bestRanked } from "./archive-years";
import { citationShardPath } from "./citations";
import { PAPER_BUDGET } from "./period";
import { monthsOf, type SearchShardFile, searchShardPath } from "./search-shards";
import { candidateMonths, candidateYears } from "./share";
import {
  type ArchiveFile,
  type CitationsFile,
  type DayFile,
  type DaySummary,
  type Paper,
  SCHEMA_VERSION,
  type StoreIndex,
  type TopRecentFile,
} from "./types";
import type { CountriesFile } from "./world";

const DATA_URL = `${import.meta.env.BASE_URL}data/`;
const MAX_PARALLEL_REQUESTS = 6;

/**
 * Day and archive files loaded (and the most cited papers of the last 12 months), kept for
 * the next periods (back to the last week after the last month, a year of the archive after
 * another): as many papers as a period loads,
 * besides those shown, which are shared. The least recently used files leave first.
 */
const loaded = new Map<string, Paper[]>();
const CACHED_PAPERS = PAPER_BUDGET;

function recall(path: string): Paper[] | undefined {
  const papers = loaded.get(path);
  if (papers !== undefined) {
    // Most recently used last.
    loaded.delete(path);
    loaded.set(path, papers);
  }
  return papers;
}

function remember(path: string, papers: Paper[]): void {
  loaded.set(path, papers);
  let total = 0;
  for (const kept of loaded.values()) total += kept.length;
  for (const [oldest, kept] of loaded) {
    if (total <= CACHED_PAPERS || oldest === path) break;
    loaded.delete(oldest);
    total -= kept.length;
  }
}

/** Forget the files loaded (tests serve other files under the same paths). */
export function forgetLoaded(): void {
  loaded.clear();
  shards.clear();
  searchShards.clear();
}

/** The citation shards asked for, by path, for the page's lifetime. */
const shards = new Map<string, Promise<CitationsFile | null>>();

/**
 * A citation shard, loaded once for the page (the counts of the papers shown, and the
 * archive's ranking of its years); `null` when it does not exist or fails, which is asked
 * for again next time. Citation counts are a bonus: without them, the papers still show,
 * and a shard that fails is only reported in the console (SRCH-10).
 */
export function citationShard(category: string, shard: string): Promise<CitationsFile | null> {
  const key = `${category}/${shard}`;
  let file = shards.get(key);
  if (file === undefined) {
    file = loadCitationShard(category, shard).catch((error: unknown) => {
      console.warn(
        `Could not load the citation shard ${citationShardPath(category, shard)}`,
        error,
      );
      shards.delete(key);
      return null;
    });
    shards.set(key, file);
  }
  return file;
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${DATA_URL}${path}`, signal ? { signal } : {});
  if (!response.ok) {
    throw new Error(`Could not load ${path} (HTTP ${response.status})`);
  }
  return (await response.json()) as T;
}

/** A file of another schema version: the site and its data do not match, asking again cannot help. */
class SchemaVersionError extends Error {}

function checkSchema(version: number, what: string): void {
  if (version !== SCHEMA_VERSION) {
    throw new SchemaVersionError(
      `Unsupported ${what} schema version ${version} (expected ${SCHEMA_VERSION})`,
    );
  }
}

/**
 * The store's index, which `index.html` preloads: this request takes the preload's response
 * while it keeps the `<link>`'s URL and `fetch`'s default mode and credentials, which its
 * `crossorigin` asks for (PERF-14).
 */
export async function loadIndex(): Promise<StoreIndex> {
  const index = await fetchJson<StoreIndex>("index.json");
  checkSchema(index.schema_version, "index");
  return index;
}

/** The papers of a day or archive file, from the files loaded before if there. */
async function loadPapers(
  path: string,
  what: string,
  signal: AbortSignal | undefined,
): Promise<Paper[]> {
  const known = recall(path);
  if (known !== undefined) return known;
  const file = await fetchJson<DayFile | ArchiveFile | TopRecentFile>(path, signal);
  checkSchema(file.schema_version, what);
  remember(path, file.papers);
  return file.papers;
}

/**
 * A day file's papers, asked for once more when it fails: a request the network or the
 * site dropped is often answered the second time. Not when the period was left, nor for a
 * file of another schema version.
 */
async function loadDay(path: string, signal: AbortSignal | undefined): Promise<Paper[]> {
  try {
    return await loadPapers(path, "day file", signal);
  } catch (error) {
    if (signal?.aborted || error instanceof SchemaVersionError) throw error;
    return loadPapers(path, "day file", signal);
  }
}

/**
 * Load the papers of the given days, most recent first, with bounded parallelism;
 * `signal` cancels the requests left (the period changed). A day file that fails twice is
 * left out, reported in the console, and its day returned among the `missing` ones, which
 * the period names (SRCH-10); when every one fails, the network or the site is down, and
 * the period fails, as it does for a file of another schema version, which a deploy that
 * went wrong serves.
 */
export async function loadDays(
  category: string,
  days: readonly DaySummary[],
  signal?: AbortSignal,
): Promise<{ papers: Paper[]; missing: string[] }> {
  const results: (Paper[] | null)[] = new Array(days.length);
  let failure: unknown;
  let next = 0;

  async function worker(): Promise<void> {
    while (next < days.length) {
      const position = next++;
      const day = days[position];
      if (day === undefined) return;
      const path = `${category}/${day.date}.json`;
      results[position] = await loadDay(path, signal).catch((error: unknown) => {
        if (signal?.aborted || error instanceof SchemaVersionError) throw error;
        console.warn(`Could not load the day file ${path}`, error);
        failure = error;
        return null;
      });
    }
  }

  await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL_REQUESTS, days.length) }, worker));
  const missing = days.filter((_, at) => results[at] === null).map(({ date }) => date);
  if (missing.length > 0 && missing.length === days.length) throw failure;
  return { papers: results.flatMap((papers) => papers ?? []), missing };
}

/** Load the archived papers of one year (highly cited older papers). */
export function loadArchive(
  category: string,
  year: number,
  signal?: AbortSignal,
): Promise<Paper[]> {
  return loadPapers(`${category}/archive/${year}.json`, "archive file", signal);
}

/** Load the most cited papers of the last 12 months, which the archive keeps apart (PROD-11). */
export function loadTopRecent(category: string, signal?: AbortSignal): Promise<Paper[]> {
  return loadPapers(`${category}/top-recent.json`, "top-recent file", signal);
}

/**
 * Load the archived papers of several years, within `budget`: past it, the best ranked by
 * citations per year of age (`bestRanked`), from the citation shards of those years, how
 * many there were in all, and how many years could not be ranked.
 */
export async function loadArchiveYears(
  category: string,
  years: readonly number[],
  budget: number,
  signal?: AbortSignal,
): Promise<{ papers: Paper[]; total: number; unranked: number }> {
  const files = await Promise.all(years.map((year) => loadArchive(category, year, signal)));
  const papers = files.flat();
  if (papers.length <= budget) return { papers, total: papers.length, unranked: 0 };
  const rankings = await Promise.all(years.map((year) => citationShard(category, String(year))));
  const counts = new Map<string, number>();
  let asOf: string | undefined;
  for (const file of rankings) {
    if (file === null) continue;
    asOf ??= file.generated_at;
    for (const [arxivId, count] of Object.entries(file.counts)) counts.set(arxivId, count);
  }
  const date = asOf === undefined ? new Date() : new Date(asOf);
  return {
    papers: bestRanked(papers, counts, date, budget),
    total: papers.length,
    // Years whose counts did not load: their papers rank last, which the page says.
    unranked: rankings.filter((file) => file === null).length,
  };
}

/**
 * The search shards asked for, by path, for the page's lifetime: apart from the day files
 * loaded, which a month of papers would push out.
 */
const searchShards = new Map<string, Promise<Paper[] | null>>();

/**
 * The papers of a month's search shard (`search-shards.ts`), loaded once for the page and
 * never cancelled, as another period may ask for it while it loads; `null` when it fails
 * (SRCH-10), which is asked for again next time.
 */
function searchShard(category: string, month: string): Promise<Paper[] | null> {
  const path = searchShardPath(category, month);
  let papers = searchShards.get(path);
  if (papers === undefined) {
    papers = fetchJson<SearchShardFile>(path)
      .then((file) => {
        checkSchema(file.schema_version, "search shard");
        return file.papers;
      })
      .catch((error: unknown) => {
        searchShards.delete(path);
        console.warn(`Could not load the search shard ${path}`, error);
        return null;
      });
    searchShards.set(path, papers);
  }
  return papers;
}

/**
 * The papers of the given days from the search shards of their months, without abstracts
 * (PERF-1), and the days of the months whose shard could not be loaded: they are left out,
 * and the period names them.
 */
export async function loadLightDays(
  category: string,
  days: readonly DaySummary[],
): Promise<{ papers: Paper[]; missing: string[] }> {
  const wanted = new Set(days.map(({ date }) => date));
  const months = monthsOf(days);
  const shards = await Promise.all(months.map((month) => searchShard(category, month)));
  const failed = new Set(months.filter((_, at) => shards[at] === null));
  return {
    papers: shards.flatMap((papers) =>
      (papers ?? []).filter((paper) => wanted.has(paper.announced)),
    ),
    missing: days.filter(({ date }) => failed.has(date.slice(0, 7))).map(({ date }) => date),
  };
}

/** What the store holds of a category, where the papers of a shared folder are looked for. */
export interface StoreHolding {
  days: readonly DaySummary[];
  archiveYears: readonly number[];
  /** Whether it keeps the most cited papers of the last 12 months apart. */
  topRecent: boolean;
}

/**
 * The papers of a shared folder (UX-46), by their arXiv ids: from the search shards of the
 * months their ids say they were announced in (without abstracts, which a card loads when
 * opened), then the archive's years, then the most cited papers of the last 12 months,
 * each asked for only for the papers still not found. The papers in the order of the ids,
 * and the ids the site's data does not hold (older than a year and not highly cited, or of
 * a file that failed to load).
 */
export async function loadPapersById(
  category: string,
  ids: readonly string[],
  holding: StoreHolding,
): Promise<{ papers: Paper[]; missing: string[] }> {
  const asked = new Set(ids);
  const found = new Map<string, Paper>();
  const wanted = (papers: readonly Paper[] | null) => {
    for (const paper of papers ?? []) {
      if (asked.has(paper.arxiv_id) && !found.has(paper.arxiv_id)) {
        found.set(paper.arxiv_id, paper);
      }
    }
  };
  const left = () => ids.filter((id) => !found.has(id));
  // A file that fails leaves its papers missing, which the page says.
  const orNone = (what: string) => (error: unknown) => {
    console.warn(`Could not load ${what}`, error);
    return null;
  };

  const held = new Set(monthsOf(holding.days));
  const months = [...new Set(ids.flatMap(candidateMonths))].filter((month) => held.has(month));
  for (const papers of await Promise.all(months.map((month) => searchShard(category, month)))) {
    wanted(papers);
  }
  const archived = new Set(holding.archiveYears);
  const years = [...new Set(left().flatMap(candidateYears))].filter((year) => archived.has(year));
  const files = await Promise.all(
    years.map((year) => loadArchive(category, year).catch(orNone(`the archive of ${year}`))),
  );
  for (const papers of files) wanted(papers);
  if (holding.topRecent && left().length > 0) {
    wanted(await loadTopRecent(category).catch(orNone("the most cited recent papers")));
  }
  return {
    papers: ids.flatMap((id) => found.get(id) ?? []),
    missing: left(),
  };
}

/**
 * A paper whole, from the day file a search shard's record names (`light`); the record
 * itself for a paper loaded whole, or when its day file no longer holds it.
 */
export async function loadWholePaper(paper: Paper): Promise<Paper> {
  if (paper.light === undefined) return paper;
  const papers = await loadPapers(paper.light, "day file", undefined);
  return papers.find(({ arxiv_id }) => arxiv_id === paper.arxiv_id) ?? paper;
}

/**
 * The country of each institution of a category's papers (`countries.json`, UX-40), for
 * Rankings' world map; `null` before the pipeline first writes it.
 */
export async function loadCountries(category: string): Promise<CountriesFile | null> {
  const path = `${category}/countries.json`;
  const response = await fetch(`${DATA_URL}${path}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Could not load ${path} (HTTP ${response.status})`);
  const file = (await response.json()) as CountriesFile;
  checkSchema(file.schema_version, "countries");
  return file;
}

/**
 * Load a shard of the citation counts of a category (see `citations.ts`), or `null` if it
 * does not exist: no counts were published yet, or none of its papers has one.
 */
export async function loadCitationShard(
  category: string,
  shard: string,
): Promise<CitationsFile | null> {
  const response = await fetch(`${DATA_URL}${citationShardPath(category, shard)}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Could not load citation counts (HTTP ${response.status})`);
  }
  const file = (await response.json()) as CitationsFile;
  checkSchema(file.schema_version, "citations file");
  return file;
}
