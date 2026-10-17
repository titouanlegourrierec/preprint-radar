/**
 * Where the papers shown come from, for Rankings' world map (UX-41): each paper placed in
 * the countries of its institutions (`countries.json`, UX-40), counted fractionally — a
 * paper of two countries counts half for each, so that collaborations are not counted
 * twice — with four ways to read the map: papers, citations, papers per million people,
 * and impact, the citations per paper over the world's.
 */

import { LOCALE } from "./locale";
import type { Paper } from "./types";

/** What colors the map, and orders the countries' table. */
export type CountryMetric = "papers" | "citations" | "per-million" | "impact";

/** Impact is said for countries of at least this many papers: under it, chance rules it. */
export const MIN_IMPACT_PAPERS = 10;
/** Papers per million people, for countries of at least this many people. */
export const MIN_POPULATION = 1_000_000;

/** `countries.json`, as the store writes it. */
export interface CountriesFile {
  schema_version: number;
  generated_at: string;
  source: string;
  /** The ISO 3166-1 alpha-2 code of each ROR id ("US"), `null` where it is placed nowhere. */
  institutions: Record<string, string | null>;
}

/** What the map knows of a country besides the papers: its name and population. */
export interface CountryFacts {
  name: string;
  population: number | null;
}

export interface CountryStats {
  /** ISO 3166-1 alpha-2 code ("CN"). */
  code: string;
  /** Its papers, a paper of several countries counting a share for each. */
  papers: number;
  /** Their citations, shared as the papers are. */
  citations: number;
  /** Papers per million people; `null` without a population or under {@link MIN_POPULATION}. */
  perMillion: number | null;
  /** Citations per paper over the world's; `null` under {@link MIN_IMPACT_PAPERS}. */
  impact: number | null;
  /** Its institutions with most papers, at most three. */
  institutions: { name: string; papers: number }[];
}

export interface WorldStats {
  /** By papers, most first. */
  countries: CountryStats[];
  /** Papers with at least one institution placed in a country. */
  placed: number;
  /** Every paper counted. */
  total: number;
}

/** The distinct countries of a paper's institutions, in their order. */
export function countriesOfPaper(
  paper: Pick<Paper, "institution_ids">,
  countryOf: (rorId: string) => string | null | undefined,
): string[] {
  const codes = (paper.institution_ids ?? []).map((id) => (id ? countryOf(id) : null));
  return [...new Set(codes.filter((code): code is string => Boolean(code)))];
}

/**
 * The countries of the papers, with what each counts: its share of the papers and of their
 * citations, its papers per million people, its impact over the papers placed, and its
 * institutions most present.
 */
export function worldStats(
  papers: readonly Paper[],
  countryOf: (rorId: string) => string | null | undefined,
  citations: ReadonlyMap<string, number>,
  facts: (code: string) => CountryFacts | undefined,
): WorldStats {
  const totals = new Map<string, { papers: number; citations: number }>();
  const names = new Map<string, Map<string, number>>();
  let placed = 0;
  let placedCitations = 0;
  for (const paper of papers) {
    const codes = countriesOfPaper(paper, countryOf);
    if (codes.length === 0) continue;
    placed++;
    const cited = citations.get(paper.arxiv_id) ?? 0;
    placedCitations += cited;
    for (const code of codes) {
      const total = totals.get(code) ?? { papers: 0, citations: 0 };
      total.papers += 1 / codes.length;
      total.citations += cited / codes.length;
      totals.set(code, total);
    }
    // Each institution placed counts the paper once, in its own country.
    const seen = new Set<string>();
    (paper.institution_ids ?? []).forEach((id, index) => {
      const name = paper.institutions?.[index];
      const code = id ? countryOf(id) : null;
      if (!(name && code) || seen.has(name)) return;
      seen.add(name);
      const counted = names.get(code) ?? new Map<string, number>();
      counted.set(name, (counted.get(name) ?? 0) + 1);
      names.set(code, counted);
    });
  }
  const average = placed > 0 ? placedCitations / placed : 0;
  const countries = [...totals].map(([code, total]): CountryStats => {
    const population = facts(code)?.population ?? null;
    return {
      code,
      papers: total.papers,
      citations: total.citations,
      perMillion:
        population !== null && population >= MIN_POPULATION
          ? total.papers / (population / 1_000_000)
          : null,
      impact:
        total.papers >= MIN_IMPACT_PAPERS && average > 0
          ? total.citations / total.papers / average
          : null,
      institutions: [...(names.get(code) ?? [])]
        .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
        .slice(0, 3)
        .map(([name, count]) => ({ name, papers: count })),
    };
  });
  countries.sort((a, b) => b.papers - a.papers || a.code.localeCompare(b.code));
  return { countries, placed, total: papers.length };
}

/** A country's value on the metric shown; `null` where the metric says nothing of it. */
export function metricValue(country: CountryStats, metric: CountryMetric): number | null {
  if (metric === "papers") return country.papers;
  if (metric === "citations") return country.citations;
  return metric === "per-million" ? country.perMillion : country.impact;
}

/** The countries in the order of a metric, highest first; those it says nothing of last. */
export function byMetric(
  countries: readonly CountryStats[],
  metric: CountryMetric,
): CountryStats[] {
  const value = (country: CountryStats) => metricValue(country, metric) ?? -1;
  return [...countries].sort((a, b) => value(b) - value(a) || b.papers - a.papers);
}

/** The impact classes, around the world's average: under 0.67, to 0.9, to 1.1, to 1.5, over. */
export const IMPACT_THRESHOLDS = [0.67, 0.9, 1.1, 1.5] as const;

/** The nice numbers a class starts at: 1, 2 and 5 times a power of ten. */
function nice(value: number): number {
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 5, 10].find((multiple) => multiple * power >= value * 0.999) ?? 10;
  return step * power;
}

/**
 * Where the classes of a heavy-tailed metric start (papers, citations): spaced evenly on a
 * logarithmic scale between its smallest and largest values, rounded to nice numbers, at
 * most `classes - 1` of them. A few countries hold most papers: an even scale would color
 * every other country alike.
 */
export function logThresholds(values: readonly number[], classes: number): number[] {
  const positive = values.filter((value) => value > 0);
  if (positive.length === 0) return [];
  const low = Math.log10(Math.min(...positive));
  const high = Math.log10(Math.max(...positive));
  const thresholds: number[] = [];
  for (let step = 1; step < classes; step++) {
    const threshold = nice(10 ** (low + ((high - low) * step) / classes));
    if (threshold > (thresholds.at(-1) ?? 0) && threshold <= 10 ** high) thresholds.push(threshold);
  }
  return thresholds;
}

/** The class of a value: how many thresholds it reaches. */
export function classOf(value: number, thresholds: readonly number[]): number {
  return thresholds.filter((threshold) => value >= threshold).length;
}

/** A share of papers or citations as shown: whole from 10 up, else to a tenth ("2.5"). */
export function formatShare(value: number): string {
  return value >= 10
    ? Math.round(value).toLocaleString(LOCALE)
    : value.toLocaleString(LOCALE, { maximumFractionDigits: 1 });
}
