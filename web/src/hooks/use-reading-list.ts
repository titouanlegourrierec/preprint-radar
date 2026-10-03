import { useEffect, useMemo, useState } from "preact/hooks";
import {
  loadReadingList,
  mergePapers,
  readPapers,
  refreshPapers,
  STORAGE_KEY,
  saveReadingList,
} from "../reading-list";
import { PaperIndex } from "../search";
import type { Paper } from "../types";

const NOT_STORED =
  "Your browser did not store the reading list (its storage is full or disabled): it lasts " +
  "until this page closes. Export it to keep it.";

/**
 * The papers saved in this browser, with a search index over them. The list follows the
 * other tabs' changes, takes the fresher records of loaded days, and can be imported.
 */
export function useReadingList(loaded: PaperIndex | null) {
  const [papers, setPapers] = useState<Paper[]>(loadReadingList);
  const [message, setMessage] = useState<string | null>(null);
  const index = useMemo(() => new PaperIndex(papers), [papers]);
  const savedIds = useMemo(() => new Set(papers.map((paper) => paper.arxiv_id)), [papers]);

  const store = (next: Paper[]) => {
    if (!saveReadingList(next)) setMessage(NOT_STORED);
    return next;
  };

  // Another tab saved or removed a paper: take its list rather than overwrite it later.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) setPapers(loadReadingList());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // A paper saved before its affiliations were read gets them once its day is loaded.
  useEffect(() => {
    if (loaded === null) return;
    setPapers((current) => {
      const fresh = refreshPapers(current, (arxivId) => loaded.get(arxivId));
      return fresh === current ? current : store(fresh);
    });
  }, [loaded]);

  const toggle = (paper: Paper) => {
    setPapers((current) =>
      store(
        current.some((saved) => saved.arxiv_id === paper.arxiv_id)
          ? current.filter((saved) => saved.arxiv_id !== paper.arxiv_id)
          : [paper, ...current],
      ),
    );
  };

  /** Add the papers of an exported list (JSON); says how many were added. */
  const importFile = async (file: File) => {
    let read: ReturnType<typeof readPapers>;
    try {
      read = readPapers(JSON.parse(await file.text()));
    } catch {
      setMessage(`${file.name} is not a reading list exported as JSON.`);
      return;
    }
    const { papers: next, added } = mergePapers(papers, read.papers);
    setPapers(store(next));
    const skipped =
      read.skipped === 1
        ? "; 1 entry that is not a paper was skipped"
        : read.skipped
          ? `; ${read.skipped} entries that are not papers were skipped`
          : "";
    setMessage(
      `${added} paper${added === 1 ? "" : "s"} added, ${read.papers.length - added} already saved${skipped}.`,
    );
  };

  return {
    papers,
    index,
    savedIds,
    toggle,
    importFile,
    message,
    dismissMessage: () => setMessage(null),
  };
}
