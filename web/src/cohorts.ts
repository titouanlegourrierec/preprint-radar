import { LOCALE } from "./locale";
import type { Cohort } from "./types";

/** The shares of its year a card names, the smallest first. */
const SHARES = [
  [1, "top_1"],
  [5, "top_5"],
  [10, "top_10"],
] as const;

/** A paper's place among its year's papers: "Top 1% of 2017", and what it means. */
export interface CohortBadge {
  text: string;
  title: string;
}

/**
 * The smallest share of its year's papers a paper's citations put it in, 1%, 5% or 10%
 * (decision 22): 300 citations do not mean the same in 2012 and in 2022. The year is that of
 * its first appearance, which the archive's papers are dated by; `null` without a count, for
 * a year the cohorts do not hold (the current one), or below the top 10%.
 */
export function cohortBadge(
  announced: string,
  citations: number | undefined,
  cohorts: Readonly<Record<string, Cohort>> | undefined,
  category: string,
  source = "Semantic Scholar",
): CohortBadge | null {
  const year = announced.slice(0, 4);
  const cohort = cohorts?.[year];
  if (citations === undefined || cohort === undefined) return null;
  const share = SHARES.find(([, key]) => cohort[key] > 0 && citations >= cohort[key])?.[0];
  if (share === undefined) return null;
  return {
    text: `Top ${share}% of ${year}`,
    title:
      `Among the ${share}% most cited of the ${cohort.papers.toLocaleString(LOCALE)} ${category} ` +
      `papers first submitted to arXiv in ${year}, by citations on ${source}`,
  };
}
