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
   * the store's records, the build merges it from `scholar.json` (`tooling/scholar.ts`).
   * Absent when unknown.
   */
  author_ids?: (string | null)[];
  /**
   * How popular the code the paper links is (`codeUrl`): not in the store's records, the
   * build merges it from `code.json` (`tooling/code.ts`) where the link is still the one
   * the card shows. Absent when unknown.
   */
  code?: CodeStats;
  /**
   * The ISO codes of the countries of its institutions ("FR"), for the country filter
   * (PROD-22): not in the store's records, the build merges them from `countries.json`
   * (`tooling/countries.ts`), by the institutions' ROR ids, as the map counts them. Absent
   * when none is known, and in reading lists saved before.
   */
  countries?: string[];
  /**
   * Only in a search shard's record (`search-shards.ts`), which has no abstract nor
   * comments: the code they link (`codeUrl`), `null` for none.
   */
  code_url?: string | null;
  /**
   * Only in a search shard's record: the path under `data/` of the day file that holds the
   * paper whole, which its card loads for the abstract.
   */
  light?: string;
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

/**
 * How popular a paper's code is (PROD-18): the stars of its GitHub repository and those it
 * gained between the last two weekly refreshes, or the likes of its Hugging Face page.
 * `shared` when other papers link the same repository, or this one a folder of it: its
 * stars are not the paper's alone.
 */
export interface CodeStats {
  stars?: number;
  gained?: number;
  likes?: number;
  shared?: boolean;
}

/** `<category>/code.json`: the stars of the code the stored papers link, by arXiv id. */
export interface CodeFile {
  schema_version: number;
  category: string;
  generated_at: string;
  /** The refresh the stars gained are counted from; `null` before a second one. */
  since: string | null;
  source: string;
  papers: Record<string, CodeStats & { url: string }>;
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

/** The most cited papers of the last 12 months, which the archive keeps apart (PROD-11). */
export interface TopRecentSummary {
  /** First day of first appearance of the 12 months they were chosen from. */
  since: string;
  count: number;
}

export interface StoreIndex {
  schema_version: number;
  generated_at: string;
  categories: Record<string, DaySummary[]>;
  /** Years of the archive of highly cited older papers; absent before the first archive. */
  archives?: Record<string, ArchiveSummary[]>;
  /** The most cited papers of the last 12 months; absent before the first archive to write them. */
  top_recent?: Record<string, TopRecentSummary>;
  /**
   * The site's index only: the version of each data file the site loads, by its path under
   * `data/`, which the build writes (`tooling/data-versions.ts`, PERF-8).
   */
  versions?: Record<string, string>;
  /**
   * The site's index only: each category's papers of each complete year, as their citations
   * rank them (`cohorts.json`, by year), which the build adds (`tooling/cohorts.ts`).
   */
  cohorts?: Record<string, Record<string, Cohort>>;
  /**
   * Each major institution's logo, by the name the site gives it: its path on the site
   * ("logos/stanford-university-1a2b3c4d.svg", PROD-23), which the build adds from the
   * hand-kept `logos.json`, the file named after its content, so never cached stale.
   */
  logos?: Record<string, string>;
}

/**
 * The papers of one year of first version, as their citations rank them (decision 22): how
 * many there are, and the citations of the last of the most cited 1%, 5% and 10%.
 */
export interface Cohort {
  papers: number;
  top_1: number;
  top_5: number;
  top_10: number;
}

/** `<category>/cohorts.json`, which the weekly archive writes. */
export interface CohortsFile {
  schema_version: number;
  category: string;
  generated_at: string;
  source: string;
  years: Record<string, Cohort>;
}

export interface ArchiveFile {
  schema_version: number;
  category: string;
  year: number;
  papers: Paper[];
}

/** `top-recent.json`: the most cited papers of the last 12 months, newest first. */
export interface TopRecentFile {
  schema_version: number;
  category: string;
  since: string;
  papers: Paper[];
}

export interface CitationsFile {
  schema_version: number;
  category: string;
  generated_at: string;
  /** Where the counts come from, e.g. "Semantic Scholar". */
  source: string;
  counts: Record<string, number>;
  /** In a shard (`src/citations.ts`): what its papers gained, from `citation-gains.json`. */
  gains?: CitationGains;
}

/** What papers gained between two weekly refreshes of their counts (CIT-9). */
export interface CitationGains {
  /** The day of the counts they are counted from, and to. */
  since: string;
  to: string;
  /** Citations gained, for each paper that gained any. */
  counts: Record<string, number>;
}

/** `<category>/citation-gains.json`, which the pipeline writes with the weekly counts. */
export interface CitationGainsFile {
  schema_version: number;
  category: string;
  since: string;
  generated_at: string;
  source: string;
  gains: Record<string, number>;
}
