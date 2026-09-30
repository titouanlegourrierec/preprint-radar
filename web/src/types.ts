/**
 * Data contracts shared with the Python pipeline (`preprint_radar.store`, schema version 1).
 */

export const SCHEMA_VERSION = 1;

export interface Paper {
  arxiv_id: string;
  /** ISO date of the announcement. */
  announced: string;
  title: string;
  authors: string[];
  primary_subject: string | null;
  subjects: string[];
  comments: string | null;
  journal_ref: string | null;
  /** Venue detected from the comments, e.g. "ECCV 2026". Absent from older records. */
  venue?: string | null;
  cross_list_from: string | null;
  html_url: string | null;
  /** `null` when not retrieved yet. */
  abstract: string | null;
  /** `null` when not retrieved yet, `[]` when none could be found. */
  affiliations: string[] | null;
  /**
   * Per author, the indices of their own affiliations in `affiliations`; `null` for an
   * author the paper does not place, `null` altogether when the paper never says who is
   * where. Absent from older records.
   */
  author_affiliations?: (number[] | null)[] | null;
  /**
   * Per affiliation, its institution according to the Research Organization Registry;
   * `null` without a confident match, `null` altogether if not looked up yet. Absent from
   * older records.
   */
  institutions?: (string | null)[] | null;
  abs_url: string;
  pdf_url: string;
}

export interface DayFile {
  schema_version: number;
  category: string;
  date: string;
  papers: Paper[];
}

export interface DaySummary {
  date: string;
  count: number;
}

export interface ArchiveSummary {
  year: number;
  count: number;
}

export interface StoreIndex {
  schema_version: number;
  generated_at: string;
  categories: Record<string, DaySummary[]>;
  /** Years of the archive of highly cited older papers; absent before the first archive. */
  archives?: Record<string, ArchiveSummary[]>;
}

export interface ArchiveFile {
  schema_version: number;
  category: string;
  year: number;
  papers: Paper[];
}

export interface CitationsFile {
  schema_version: number;
  category: string;
  generated_at: string;
  /** Where the counts come from, e.g. "Semantic Scholar". */
  source: string;
  counts: Record<string, number>;
}
