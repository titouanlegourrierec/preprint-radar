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
  /**
   * Venue detected from the comments, e.g. "ECCV 2026", else the one it was published at
   * according to Semantic Scholar (merged in by the build). Absent from older records.
   */
  venue?: string | null;
  /**
   * DOI of the published version, from Semantic Scholar: not in the store's records, the
   * build merges it from `scholar.json` (`tooling/scholar.ts`). Absent when unknown.
   */
  doi?: string | null;
  /**
   * Semantic Scholar's id of each author, in order, `null` for one it has none for: not in
   * the store's records, the build merges it from `scholar.json`, giving an author without
   * one the id of the only person of that name (`tooling/scholar.ts`, AFF-H). Absent when
   * unknown.
   */
  author_ids?: (string | null)[];
  cross_list_from: string | null;
  html_url: string | null;
  /** `null` when not retrieved yet. */
  abstract: string | null;
  /**
   * Version of the pipeline's HTML extraction that gave the affiliations. Absent when they
   * came from elsewhere or were read before versions were kept.
   */
  extractor?: number;
  /** Its authors (or arXiv) withdrew it, as its comments say; absent otherwise. */
  withdrawn?: boolean;
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
  /**
   * Per institution, its ROR id ("03vek6s52"), parallel to `institutions`. Absent for
   * institutions named before ids were kept.
   */
  institution_ids?: (string | null)[] | null;
  /**
   * Where the affiliations and the institutions came from, and when (`models.Provenance`).
   * The app does not read it, and reading lists do not keep it.
   */
  provenance?: {
    affiliations?: Provenance;
    institutions?: Provenance;
  };
  abs_url: string;
  pdf_url: string;
}

/** Where a field came from: affiliations "html", "api" or "openalex"; institutions "ror" or "openalex". */
export interface Provenance {
  source: string;
  /** The day it was read; absent for what was read before provenance was kept. */
  at?: string;
}

/** `<category>/scholar.json`: what Semantic Scholar knows of the stored papers. */
export interface ScholarFile {
  schema_version: number;
  category: string;
  generated_at: string;
  source: string;
  papers: Record<string, { doi?: string; venue?: string; author_ids?: (string | null)[] }>;
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
