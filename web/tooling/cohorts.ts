import type { Cohort } from "../src/types";

/**
 * The site's `index.json` with each category's cohorts, the papers of each complete year as
 * their citations rank them, from `<category>/cohorts.json` (decision 22): a card says "Top
 * 1% of 2017" from them, and they weigh a kilobyte, which the index preloaded carries rather
 * than another request.
 */
export function withCohorts(
  indexText: string,
  cohorts: Record<string, Record<string, Cohort>>,
): string {
  if (Object.keys(cohorts).length === 0) return indexText;
  const index = JSON.parse(indexText) as Record<string, unknown>;
  index.cohorts = cohorts;
  return `${JSON.stringify(index)}\n`;
}
