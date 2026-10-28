import { dayFilePath, lightRecord, searchShardPath } from "../src/search-shards";
import type { CodeFile, DayFile, Paper, ScholarFile, StoreIndex } from "../src/types";
import { SCHEMA_VERSION } from "../src/types";
import type { CountriesFile } from "../src/world";
import type { ReadJson } from "./citation-shards";
import { mergeCode } from "./code";
import { mergeCountries } from "./countries";
import { mergeScholar } from "./scholar";

/**
 * The search shards of a store (`src/search-shards.ts`), as JSON text by path under
 * `data/`: for each category, one per month of its day files, their records as the site
 * gets them (with what `scholar.json`, `code.json` and `countries.json` know) but for their
 * abstract and comments.
 */
export function searchShardFiles(read: ReadJson): Map<string, string> {
  const files = new Map<string, string>();
  const index = read("index.json") as StoreIndex | null;
  if (index === null) return files;
  for (const [category, days] of Object.entries(index.categories)) {
    const scholar = read(`${category}/scholar.json`) as ScholarFile | null;
    const code = read(`${category}/code.json`) as CodeFile | null;
    const countries = read(`${category}/countries.json`) as CountriesFile | null;
    const months = new Map<string, Paper[]>();
    for (const { date } of days) {
      const path = dayFilePath(category, date);
      const file = read(path) as DayFile | null;
      if (file === null) continue;
      if (scholar !== null) mergeScholar(file.papers, scholar);
      if (code !== null) mergeCode(file.papers, code);
      if (countries !== null) mergeCountries(file.papers, countries);
      const month = date.slice(0, 7);
      const papers = months.get(month) ?? [];
      papers.push(...file.papers.map((paper) => lightRecord(paper, path)));
      months.set(month, papers);
    }
    for (const [month, papers] of months) {
      files.set(
        searchShardPath(category, month),
        JSON.stringify({ schema_version: SCHEMA_VERSION, category, month, papers }),
      );
    }
  }
  return files;
}
