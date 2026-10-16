import { describe, expect, it } from "vitest";
import {
  byMetric,
  classOf,
  countriesOfPaper,
  formatShare,
  logThresholds,
  metricValue,
  worldStats,
} from "../src/world";
import { makePaper } from "./fixtures";

const COUNTRIES: Record<string, string | null> = {
  "0mit00000": "US",
  "0cmu00000": "US",
  "0tsing000": "CN",
  "0oxf00000": "GB",
  "0nowhere0": null,
};
const countryOf = (id: string) => COUNTRIES[id];
const FACTS: Record<string, { name: string; population: number | null }> = {
  US: { name: "United States", population: 330_000_000 },
  CN: { name: "China", population: 1_400_000_000 },
  GB: { name: "United Kingdom", population: null },
};

/** A paper at these institutions, each named after its id. */
function at(arxivId: string, ...ids: (string | null)[]) {
  return makePaper({
    arxiv_id: arxivId,
    affiliations: ids.map((id) => id ?? "Somewhere"),
    institutions: ids.map((id) => id ?? "Somewhere"),
    institution_ids: ids,
  });
}

describe("countriesOfPaper", () => {
  it("places a paper in each country of its institutions, once", () => {
    expect(
      countriesOfPaper(at("2609.00001", "0mit00000", "0tsing000", "0cmu00000"), countryOf),
    ).toEqual(["US", "CN"]);
    expect(countriesOfPaper(at("2609.00002", "0nowhere0", null, "0unknown0"), countryOf)).toEqual(
      [],
    );
    expect(countriesOfPaper(makePaper({ arxiv_id: "2609.00003" }), countryOf)).toEqual([]);
  });
});

describe("worldStats", () => {
  const papers = [
    at("2609.00001", "0mit00000", "0tsing000"),
    at("2609.00002", "0mit00000", "0cmu00000"),
    at("2609.00003", "0oxf00000"),
    at("2609.00004", "0nowhere0"),
  ];
  const citations = new Map([
    ["2609.00001", 10],
    ["2609.00002", 4],
    ["2609.00004", 100],
  ]);
  const stats = worldStats(papers, countryOf, citations, (code) => FACTS[code]);

  it("counts a paper of several countries as a share of each (UX-41)", () => {
    expect(stats.placed).toBe(3);
    expect(stats.total).toBe(4);
    expect(stats.countries.map(({ code, papers }) => [code, papers])).toEqual([
      ["US", 1.5],
      ["GB", 1],
      ["CN", 0.5],
    ]);
    const us = stats.countries[0];
    expect(us?.citations).toBe(9);
    // Its institutions, each counting a paper once.
    expect(us?.institutions).toEqual([
      { name: "0mit00000", papers: 2 },
      { name: "0cmu00000", papers: 1 },
    ]);
  });

  it("says papers per million people and impact where they mean something", () => {
    const us = stats.countries.find(({ code }) => code === "US");
    expect(us?.perMillion).toBeCloseTo(1.5 / 330);
    // Under 10 papers, no impact; no population, no rate.
    expect(us?.impact).toBeNull();
    expect(stats.countries.find(({ code }) => code === "GB")?.perMillion).toBeNull();

    const many = Array.from({ length: 12 }, (_, index) =>
      at(`2609.1${String(index).padStart(4, "0")}`, index < 10 ? "0mit00000" : "0tsing000"),
    );
    const cited = new Map(many.map((paper, index) => [paper.arxiv_id, index < 10 ? 6 : 0]));
    const world = worldStats(many, countryOf, cited, (code) => FACTS[code]);
    // The world's papers average 5 citations, the United States' 6.
    expect(world.countries[0]?.impact).toBeCloseTo(1.2);
    expect(worldStats([], countryOf, cited, () => undefined).countries).toEqual([]);
  });

  it("orders the countries by a metric, those it says nothing of last", () => {
    const [us, gb, cn] = stats.countries;
    if (!(us && gb && cn)) throw new Error("three countries");
    expect(metricValue(us, "papers")).toBe(1.5);
    expect(metricValue(us, "citations")).toBe(9);
    expect(metricValue(gb, "per-million")).toBeNull();
    expect(metricValue(us, "impact")).toBeNull();
    expect(byMetric(stats.countries, "citations").map(({ code }) => code)).toEqual([
      "US",
      "CN",
      "GB",
    ]);
    expect(byMetric(stats.countries, "per-million").map(({ code }) => code)).toEqual([
      "US",
      "CN",
      "GB",
    ]);
  });
});

describe("classes", () => {
  it("are spaced on a logarithmic scale, at nice numbers", () => {
    expect(logThresholds([1, 3, 40, 7800], 6)).toEqual([5, 20, 100, 500, 2000]);
    expect(logThresholds([0, 0], 6)).toEqual([]);
    // A single value: no class to tell apart.
    expect(logThresholds([12], 6)).toEqual([]);
  });

  it("count the thresholds a value reaches", () => {
    expect(classOf(3, [5, 20, 100])).toBe(0);
    expect(classOf(20, [5, 20, 100])).toBe(2);
    expect(classOf(7800, [5, 20, 100])).toBe(3);
  });
});

it("formats a share of papers whole from 10 up", () => {
  expect(formatShare(7784.4)).toBe("7,784");
  expect(formatShare(2.5)).toBe("2.5");
  expect(formatShare(0.333)).toBe("0.3");
});
