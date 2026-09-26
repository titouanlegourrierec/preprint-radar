import { useMemo, useState } from "preact/hooks";
import { loadReadingList, saveReadingList } from "../reading-list";
import { PaperIndex } from "../search";
import type { Paper } from "../types";

/** The papers saved in this browser, with a search index over them. */
export function useReadingList() {
  const [papers, setPapers] = useState<Paper[]>(loadReadingList);
  const index = useMemo(() => new PaperIndex(papers), [papers]);
  const savedIds = useMemo(() => new Set(papers.map((paper) => paper.arxiv_id)), [papers]);

  const toggle = (paper: Paper) => {
    setPapers((current) => {
      const next = current.some((saved) => saved.arxiv_id === paper.arxiv_id)
        ? current.filter((saved) => saved.arxiv_id !== paper.arxiv_id)
        : [paper, ...current];
      saveReadingList(next);
      return next;
    });
  };

  return { papers, index, savedIds, toggle };
}
