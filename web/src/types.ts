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
  cross_list_from: string | null;
  html_url: string | null;
  /** `null` when not retrieved yet. */
  abstract: string | null;
  /** `null` when not retrieved yet, `[]` when none could be found. */
  affiliations: string[] | null;
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

export interface StoreIndex {
  schema_version: number;
  generated_at: string;
  categories: Record<string, DaySummary[]>;
}
