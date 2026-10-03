import { citationShardPath } from "./citations";
import { PAPER_BUDGET } from "./period";
import {
  type ArchiveFile,
  type CitationsFile,
  type DayFile,
  type DaySummary,
  type Paper,
  SCHEMA_VERSION,
  type StoreIndex,
} from "./types";

const DATA_URL = `${import.meta.env.BASE_URL}data/`;
const MAX_PARALLEL_REQUESTS = 6;

/**
 * Day and archive files loaded, kept for the next periods (back to the last 5 days after
 * the last 20, a year of the archive after another): as many papers as a period loads,
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
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${DATA_URL}${path}`, signal ? { signal } : {});
  if (!response.ok) {
    throw new Error(`Could not load ${path} (HTTP ${response.status})`);
  }
  return (await response.json()) as T;
}

function checkSchema(version: number, what: string): void {
  if (version !== SCHEMA_VERSION) {
    throw new Error(`Unsupported ${what} schema version ${version} (expected ${SCHEMA_VERSION})`);
  }
}

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
  const file = await fetchJson<DayFile | ArchiveFile>(path, signal);
  checkSchema(file.schema_version, what);
  remember(path, file.papers);
  return file.papers;
}

/**
 * Load the papers of the given days, most recent first, with bounded parallelism;
 * `signal` cancels the requests left (the period changed).
 */
export async function loadDays(
  category: string,
  days: DaySummary[],
  signal?: AbortSignal,
): Promise<Paper[]> {
  const results: Paper[][] = new Array(days.length);
  let next = 0;

  async function worker(): Promise<void> {
    while (next < days.length) {
      const position = next++;
      const day = days[position];
      if (day === undefined) return;
      results[position] = await loadPapers(`${category}/${day.date}.json`, "day file", signal);
    }
  }

  await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL_REQUESTS, days.length) }, worker));
  return results.flat();
}

/** Load the archived papers of one year (highly cited older papers). */
export function loadArchive(
  category: string,
  year: number,
  signal?: AbortSignal,
): Promise<Paper[]> {
  return loadPapers(`${category}/archive/${year}.json`, "archive file", signal);
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
