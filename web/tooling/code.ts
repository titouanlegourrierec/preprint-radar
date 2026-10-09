import { codeUrl } from "../src/code";
import type { CodeFile, CodeStats } from "../src/types";
import type { StoredPaper } from "./scholar";

/**
 * The popularity of each paper's code from `code.json`, in place: its stars (and those it
 * gained in the week) or likes, whether they are shared. Only where the record's link is
 * the one the card shows: a new version that links other code waits for the next refresh.
 */
export function mergeCode(papers: StoredPaper[], code: CodeFile): void {
  for (const paper of papers) {
    const record = code.papers[paper.arxiv_id];
    const shown = codeUrl({ abstract: paper.abstract ?? null, comments: paper.comments ?? null });
    if (record === undefined || shown !== record.url) continue;
    const { url: _url, ...stats } = record;
    paper.code = stats satisfies CodeStats;
  }
}
