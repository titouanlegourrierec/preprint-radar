import { type AbstractsFile, lightRecord } from "../src/search-shards";
import type { Paper } from "../src/types";

/**
 * A paper file's light version and its abstracts, as JSON text, from the file as the site
 * gets it (its records with what `scholar.json`, `code.json` and `countries.json` know).
 */
export function splitPaperFile(text: string, path: string): { light: string; abstracts: string } {
  const file = JSON.parse(text) as { schema_version: number; papers: Paper[] } & Record<
    string,
    unknown
  >;
  const abstracts: AbstractsFile["abstracts"] = {};
  for (const paper of file.papers) {
    if (paper.abstract !== null || paper.comments !== null) {
      abstracts[paper.arxiv_id] = [paper.abstract, paper.comments];
    }
  }
  return {
    light: JSON.stringify({
      ...file,
      papers: file.papers.map((paper) => lightRecord(paper, path)),
    }),
    abstracts: JSON.stringify({ schema_version: file.schema_version, abstracts }),
  };
}
