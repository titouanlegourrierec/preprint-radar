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

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${DATA_URL}${path}`);
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

/** Load the papers of the given days, most recent first, with bounded parallelism. */
export async function loadDays(category: string, days: DaySummary[]): Promise<Paper[]> {
  const results: Paper[][] = new Array(days.length);
  let next = 0;

  async function worker(): Promise<void> {
    while (next < days.length) {
      const position = next++;
      const day = days[position];
      if (day === undefined) return;
      const file = await fetchJson<DayFile>(`${category}/${day.date}.json`);
      checkSchema(file.schema_version, "day file");
      results[position] = file.papers;
    }
  }

  await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL_REQUESTS, days.length) }, worker));
  return results.flat();
}

/** Load the archived papers of one year (highly cited older papers). */
export async function loadArchive(category: string, year: number): Promise<Paper[]> {
  const file = await fetchJson<ArchiveFile>(`${category}/archive/${year}.json`);
  checkSchema(file.schema_version, "archive file");
  return file.papers;
}

/** Load the citation counts of a category, or `null` if none were published yet. */
export async function loadCitations(category: string): Promise<CitationsFile | null> {
  const response = await fetch(`${DATA_URL}${category}/citations.json`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Could not load citation counts (HTTP ${response.status})`);
  }
  const file = (await response.json()) as CitationsFile;
  checkSchema(file.schema_version, "citations file");
  return file;
}
