import { arxivIdOf } from "./search";
import type { Paper } from "./types";

export const STORAGE_KEY = "preprint-radar:reading-list";
/** Version of the stored list and of its JSON export; the first lists were a bare array. */
const FORMAT_VERSION = 1;

/** The reading list as stored and exported. */
export interface ReadingListFile {
  version: typeof FORMAT_VERSION;
  papers: Paper[];
  /** The saved searches, exported with the papers (`saved-searches.ts` reads them). */
  searches?: unknown[];
}

const isString = (value: unknown): value is string => typeof value === "string";
const isStringOrNull = (value: unknown): value is string | null =>
  value === null || isString(value);
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);

const ARXIV = "https://arxiv.org";

/**
 * The record as a paper, or `null` when it is not one: what the store writes, read as the
 * Python `Paper.from_record` does. Saved lists and imported files are untrusted: one bad
 * entry must not break the page. Fields that older records lack become `null` (or `[]`
 * for subjects), and a mapping out of step with the authors is dropped. Links come from
 * the arXiv id, as the store makes them, never from the file: an imported `javascript:`
 * address would run on a click (SEC-2); an HTML page is kept on arxiv.org only.
 */
export function toPaper(value: unknown): Paper | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  const { arxiv_id, announced, title, authors } = record;
  if (
    !isString(arxiv_id) ||
    arxivIdOf(arxiv_id) !== arxiv_id ||
    !isString(announced) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(announced) ||
    !isString(title) ||
    !isStringArray(authors)
  ) {
    return null;
  }
  const html = record.html_url;
  const nullable = (key: string) =>
    isStringOrNull(record[key]) ? (record[key] as string | null) : null;
  const affiliations = isStringArray(record.affiliations) ? record.affiliations : null;
  const mapping = record.author_affiliations;
  const mappingFits =
    Array.isArray(mapping) &&
    mapping.length === authors.length &&
    mapping.every(
      (entry) =>
        entry === null ||
        (Array.isArray(entry) &&
          entry.every(
            (index) => Number.isInteger(index) && index >= 0 && index < (affiliations?.length ?? 0),
          )),
    );
  const institutions = record.institutions;
  const institutionsFit =
    Array.isArray(institutions) &&
    institutions.length === (affiliations?.length ?? -1) &&
    institutions.every(isStringOrNull);
  const ids = record.institution_ids;
  const idsFit =
    institutionsFit &&
    Array.isArray(ids) &&
    ids.length === institutions.length &&
    ids.every(isStringOrNull);
  return {
    arxiv_id,
    announced,
    title,
    authors,
    primary_subject: nullable("primary_subject"),
    subjects: isStringArray(record.subjects) ? record.subjects : [],
    comments: nullable("comments"),
    journal_ref: nullable("journal_ref"),
    venue: nullable("venue"),
    ...(isString(record.doi) ? { doi: record.doi } : {}),
    cross_list_from: nullable("cross_list_from"),
    html_url: isString(html) && html.startsWith(`${ARXIV}/html/`) ? html : null,
    abstract: nullable("abstract"),
    ...(typeof record.extractor === "number" ? { extractor: record.extractor } : {}),
    ...(record.withdrawn === true ? { withdrawn: true } : {}),
    affiliations,
    author_affiliations: mappingFits ? (mapping as (number[] | null)[]) : null,
    institutions: institutionsFit ? (institutions as (string | null)[]) : null,
    ...(idsFit ? { institution_ids: ids as (string | null)[] } : {}),
    abs_url: `${ARXIV}/abs/${arxiv_id}`,
    pdf_url: `${ARXIV}/pdf/${arxiv_id}`,
  };
}

/**
 * The papers of a stored list or an exported file: the current format, or the bare array
 * of the first versions. Entries that are not papers are skipped, and a paper is kept once.
 */
export function readPapers(value: unknown): { papers: Paper[]; skipped: number } {
  const entries: unknown[] = Array.isArray(value)
    ? value
    : typeof value === "object" &&
        value !== null &&
        Array.isArray((value as ReadingListFile).papers)
      ? (value as ReadingListFile).papers
      : [];
  const papers = new Map<string, Paper>();
  let skipped = 0;
  for (const entry of entries) {
    const paper = toPaper(entry);
    if (paper === null) skipped++;
    else if (!papers.has(paper.arxiv_id)) papers.set(paper.arxiv_id, paper);
  }
  return { papers: [...papers.values()], skipped };
}

/** The reading list as a file to export, which {@link readPapers} reads back. */
export function readingListFile(papers: Paper[], searches?: unknown[]): ReadingListFile {
  return { version: FORMAT_VERSION, papers, ...(searches?.length ? { searches } : {}) };
}

/** Papers saved by the user, persisted in the browser (full records, so they survive data pruning). */
export function loadReadingList(): Paper[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? readPapers(JSON.parse(raw)).papers : [];
  } catch {
    return [];
  }
}

/**
 * Store the list; `false` when the browser refused (storage full or disabled), the list
 * then lasting only as long as the page.
 */
export function saveReadingList(papers: Paper[]): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(readingListFile(papers)));
    return true;
  } catch {
    return false;
  }
}

/** The saved papers, followed by the imported ones not saved yet. */
export function mergePapers(saved: Paper[], imported: Paper[]): { papers: Paper[]; added: number } {
  const known = new Set(saved.map((paper) => paper.arxiv_id));
  const added = imported.filter((paper) => !known.has(paper.arxiv_id));
  return { papers: [...saved, ...added], added: added.length };
}

/**
 * The saved papers with the records of `loaded` where it holds them: a paper saved before
 * its affiliations were read gets them. The same array when nothing changed.
 */
export function refreshPapers(
  saved: Paper[],
  loaded: (arxivId: string) => Paper | undefined,
): Paper[] {
  let changed = false;
  const papers = saved.map((paper) => {
    const fresh = loaded(paper.arxiv_id);
    if (fresh === undefined || JSON.stringify(fresh) === JSON.stringify(paper)) return paper;
    changed = true;
    return fresh;
  });
  return changed ? papers : saved;
}
