import { describe, expect, it } from "vitest";
import { cohortBadge } from "../src/cohorts";
import type { Cohort } from "../src/types";
import { withCohorts } from "../tooling/cohorts";

const COHORTS: Record<string, Cohort> = {
  "2017": { papers: 5_701, top_1: 2_020, top_5: 650, top_10: 408 },
  // A year of few papers, whose top 10% are not cited: no badge says it.
  "2010": { papers: 9, top_1: 3, top_5: 3, top_10: 0 },
};

describe("cohortBadge (decision 22)", () => {
  it("names the smallest share of its year a paper is in", () => {
    expect(cohortBadge("2017-03-02", 2_020, COHORTS, "cs.CV")).toEqual({
      text: "Top 1% of 2017",
      title:
        "Among the 1% most cited of the 5,701 cs.CV papers first submitted to arXiv in 2017, " +
        "by citations on Semantic Scholar",
    });
    expect(cohortBadge("2017-03-02", 2_019, COHORTS, "cs.CV")?.text).toBe("Top 5% of 2017");
    expect(cohortBadge("2017-03-02", 408, COHORTS, "cs.CV", "OpenAlex")?.title).toMatch(
      /by citations on OpenAlex$/,
    );
    expect(cohortBadge("2017-03-02", 408, COHORTS, "cs.CV")?.text).toBe("Top 10% of 2017");
  });

  it("says nothing below the top 10%, without a count, or for a year it does not hold", () => {
    expect(cohortBadge("2017-03-02", 407, COHORTS, "cs.CV")).toBeNull();
    expect(cohortBadge("2017-03-02", undefined, COHORTS, "cs.CV")).toBeNull();
    expect(cohortBadge("2026-10-21", 9_000, COHORTS, "cs.CV")).toBeNull();
    expect(cohortBadge("2017-03-02", 9_000, undefined, "cs.CV")).toBeNull();
    // A share whose last paper is not cited is no badge for an uncited one.
    expect(cohortBadge("2010-05-01", 0, COHORTS, "cs.CV")).toBeNull();
    expect(cohortBadge("2010-05-01", 3, COHORTS, "cs.CV")?.text).toBe("Top 1% of 2010");
  });
});

describe("withCohorts", () => {
  it("adds each category's cohorts to the site's index, and leaves it without any", () => {
    const index = '{"schema_version":1,"categories":{}}\n';
    expect(JSON.parse(withCohorts(index, { "cs.CV": COHORTS }))).toEqual({
      schema_version: 1,
      categories: {},
      cohorts: { "cs.CV": COHORTS },
    });
    expect(withCohorts(index, {})).toBe(index);
  });
});
