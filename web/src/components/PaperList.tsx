import { useEffect, useRef, useState } from "preact/hooks";
import type { SearchResult } from "../search";
import type { Paper } from "../types";
import { PaperCard } from "./PaperCard";

const PAGE_SIZE = 40;

interface Props {
  results: SearchResult[];
  savedIds: ReadonlySet<string>;
  onToggleSaved: (paper: Paper) => void;
  onAuthor: (author: string) => void;
  onAffiliation: (affiliation: string) => void;
}

/** Render results incrementally: the next page is added when the end of the list is visible. */
export function PaperList({ results, savedIds, onToggleSaved, onAuthor, onAffiliation }: Props) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const sentinel = useRef<HTMLDivElement>(null);

  // Reset paging whenever the results change.
  useEffect(() => setVisible(PAGE_SIZE), [results]);

  useEffect(() => {
    const element = sentinel.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible((count) => count + PAGE_SIZE);
        }
      },
      { rootMargin: "800px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <div class="paper-list">
        {results.slice(0, visible).map(({ paper, highlights }) => (
          <PaperCard
            key={paper.arxiv_id}
            paper={paper}
            highlights={highlights}
            saved={savedIds.has(paper.arxiv_id)}
            onToggleSaved={onToggleSaved}
            onAuthor={onAuthor}
            onAffiliation={onAffiliation}
          />
        ))}
      </div>
      <div ref={sentinel} aria-hidden="true" />
    </>
  );
}
