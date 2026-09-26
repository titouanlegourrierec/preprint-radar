import type { ComponentChild } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { papersPerDay } from "../day-groups";
import { formatShortDay } from "../format";
import type { SearchResult } from "../search";
import type { Paper } from "../types";
import { PaperCard } from "./PaperCard";

const PAGE_SIZE = 40;

interface Props {
  results: SearchResult[];
  /** Insert a heading before each day; needs results in announcement order. */
  groupByDay: boolean;
  /** Paper of a shared `?paper=` link: its card is expanded and scrolled into view. */
  openId: string | null;
  linkTo: (paper: Paper) => string;
  onOpenPaper: (arxivId: string) => void;
  showAbstracts: boolean;
  savedIds: ReadonlySet<string>;
  onToggleSaved: (paper: Paper) => void;
  onAuthor: (author: string) => void;
  onAffiliation: (affiliation: string) => void;
}

/** Render results incrementally: the next page is added when the end of the list is visible. */
export function PaperList({
  results,
  groupByDay,
  openId,
  linkTo,
  onOpenPaper,
  showAbstracts,
  savedIds,
  onToggleSaved,
  onAuthor,
  onAffiliation,
}: Props) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const sentinel = useRef<HTMLDivElement>(null);

  // Reset paging whenever the results change, keeping a shared link's target in reach.
  useEffect(() => {
    const target = openId ? results.findIndex(({ paper }) => paper.arxiv_id === openId) : -1;
    setVisible(Math.max(PAGE_SIZE, Math.ceil((target + 1) / PAGE_SIZE) * PAGE_SIZE));
  }, [results, openId]);

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

  const days = useMemo(() => papersPerDay(results), [results]);
  const withDays = groupByDay && days.size > 1;

  const rows: ComponentChild[] = [];
  let lastDay: string | null = null;
  for (const { paper, highlights } of results.slice(0, visible)) {
    if (withDays && paper.announced !== lastDay) {
      lastDay = paper.announced;
      const count = days.get(paper.announced) ?? 0;
      rows.push(
        <div key={`day:${paper.announced}`} class="day-heading">
          {formatShortDay(paper.announced)}
          <span class="day-heading__count">
            · {count} paper{count === 1 ? "" : "s"}
          </span>
        </div>,
      );
    }
    rows.push(
      <PaperCard
        key={paper.arxiv_id}
        paper={paper}
        highlights={highlights}
        showAbstract={showAbstracts}
        saved={savedIds.has(paper.arxiv_id)}
        isTarget={paper.arxiv_id === openId}
        permalink={linkTo(paper)}
        onOpen={onOpenPaper}
        onToggleSaved={onToggleSaved}
        onAuthor={onAuthor}
        onAffiliation={onAffiliation}
      />,
    );
  }

  return (
    <>
      <div class="paper-list">{rows}</div>
      <div ref={sentinel} aria-hidden="true" />
    </>
  );
}
