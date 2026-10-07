import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { dayGroups } from "../day-groups";
import { countOf, formatShortDay } from "../format";
import { hasModifier, isTyping } from "../keyboard";
import { nextFocusIndex, nextPage, PAGE_SIZE, pageCount } from "../paging";
import type { NameFilter, NameHighlights, SearchResult } from "../search";
import type { Paper } from "../types";
import { PaperCard } from "./PaperCard";

interface Props {
  results: SearchResult[];
  /** What makes a new list (`listKey`): its paging starts over only when this changes. */
  resetKey: string;
  /** The names filtered on, which cards mark in their author and affiliation lines. */
  nameHighlights: NameHighlights;
  /** Insert a heading before each day; needs results in announcement order. */
  groupByDay: boolean;
  /** Paper of a shared `?paper=` link: its card is expanded and scrolled into view. */
  openId: string | null;
  linkTo: (paper: Paper) => string;
  onOpenPaper: (arxivId: string) => void;
  /** The paper of the shared link was folded. */
  onClosePaper: () => void;
  onShowInGraph?: ((paper: Paper) => void) | undefined;
  citations: ReadonlyMap<string, number>;
  citationsNote?: string | undefined;
  /** What a paper gained in the last week of counts, as its card says it (CIT-9). */
  gainOf?: ((arxivId: string) => { text: string; title: string } | undefined) | undefined;
  showAbstracts: boolean;
  savedIds: ReadonlySet<string>;
  onToggleSaved: (paper: Paper) => void;
  /** Papers marked seen, and how to mark one; absent where papers are not triaged. */
  seenIds?: ReadonlySet<string> | undefined;
  onToggleSeen?: ((arxivId: string) => void) | undefined;
  onAuthor: (author: string) => void;
  onAffiliation: (filter: NameFilter) => void;
}

/** Render results incrementally: the next page is added when the end of the list is visible. */
export function PaperList({
  results,
  resetKey,
  nameHighlights,
  groupByDay,
  openId,
  linkTo,
  onOpenPaper,
  onClosePaper,
  onShowInGraph,
  citations,
  citationsNote,
  gainOf,
  showAbstracts,
  savedIds,
  onToggleSaved,
  seenIds,
  onToggleSeen,
  onAuthor,
  onAffiliation,
}: Props) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const sentinel = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);

  // A card marked seen while seen papers are hidden, or unsaved from the reading list,
  // leaves the list and takes the focus with it: once the list is drawn again, the card now
  // at its place takes it, so that j and x go on (UX-23).
  const refocusAfter = (index: number) =>
    setTimeout(() => {
      if (!list.current || document.activeElement !== document.body) return;
      const cards = list.current.querySelectorAll<HTMLElement>("article.paper");
      cards[nextFocusIndex(cards.length, index)]?.focus();
    }, 0);

  // Triage from the keyboard: j and k move between papers, o (or Enter on a paper) opens
  // it, s saves it, x marks it seen. Keys typed in a field are left alone.
  const byId = useMemo(
    () => new Map(results.map(({ paper }) => [paper.arxiv_id, paper])),
    [results],
  );
  const actions = useRef({ byId, onToggleSaved, onToggleSeen });
  actions.current = { byId, onToggleSaved, onToggleSeen };
  // The results' count, for the observer that adds pages, set up once.
  const total = useRef(results.length);
  total.current = results.length;
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || hasModifier(event) || isTyping(event.target) || !list.current)
        return;
      const cards = [...list.current.querySelectorAll<HTMLElement>("article.paper")];
      const current = document.activeElement?.closest<HTMLElement>("article.paper") ?? null;
      const index = current ? cards.indexOf(current) : -1;
      const paper = current ? actions.current.byId.get(current.dataset.arxivId ?? "") : undefined;
      const onCard = current !== null && document.activeElement === current;
      if (event.key === "j" || event.key === "k") {
        const next = cards[event.key === "j" ? index + 1 : Math.max(index - 1, 0)];
        if (!next) return;
        next.focus();
        next.scrollIntoView({ block: "nearest" });
      } else if (event.key === "o" || (event.key === "Enter" && onCard)) {
        current?.querySelector<HTMLButtonElement>(".paper__more")?.click();
      } else if (event.key === "s" && paper) {
        actions.current.onToggleSaved(paper);
        refocusAfter(index);
      } else if (event.key === "x" && paper && actions.current.onToggleSeen) {
        actions.current.onToggleSeen(paper.arxiv_id);
        refocusAfter(index);
      } else {
        return;
      }
      event.preventDefault();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  // A new list starts over at one page; the same list keeps its cards when one leaves it
  // or counts rank it (UX-23). A shared link's target stays in reach.
  const listShown = useRef(resetKey);
  useEffect(() => {
    const keyChanged = listShown.current !== resetKey;
    listShown.current = resetKey;
    const targetIndex = openId ? results.findIndex(({ paper }) => paper.arxiv_id === openId) : -1;
    setVisible((visible) => pageCount({ keyChanged, visible, targetIndex }));
  }, [results, openId, resetKey]);

  useEffect(() => {
    const element = sentinel.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible((count) => nextPage(count, total.current));
        }
      },
      { rootMargin: "800px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const groups = useMemo(() => dayGroups(results), [results]);
  const withDays = groupByDay && groups.length > 1;
  const [folded, setFolded] = useState<ReadonlySet<string>>(new Set());
  const toggleDay = (day: string) => (event: Event) => {
    event.preventDefault();
    setFolded((current) => {
      const next = new Set(current);
      if (!next.delete(day)) next.add(day);
      return next;
    });
  };

  // A card's own Seen and ☆ buttons hand the focus on too, when the card leaves.
  const cardIndex = (arxivId: string) =>
    [...(list.current?.querySelectorAll<HTMLElement>("article.paper") ?? [])].findIndex(
      (card) => card.dataset.arxivId === arxivId,
    );
  const toggleSeen =
    onToggleSeen &&
    ((arxivId: string) => {
      const index = cardIndex(arxivId);
      onToggleSeen(arxivId);
      refocusAfter(index);
    });
  const toggleSaved = (paper: Paper) => {
    const index = cardIndex(paper.arxiv_id);
    onToggleSaved(paper);
    refocusAfter(index);
  };
  // So does folding the paper a link opened: seen while seen papers are hidden, it stays
  // only as long as it is open.
  const closePaper = () => {
    const index = openId ? cardIndex(openId) : -1;
    onClosePaper();
    refocusAfter(index);
  };

  const card = ({ paper, highlights }: SearchResult) => (
    <PaperCard
      key={paper.arxiv_id}
      paper={paper}
      highlights={highlights}
      nameHighlights={nameHighlights}
      showAbstract={showAbstracts}
      saved={savedIds.has(paper.arxiv_id)}
      seen={seenIds?.has(paper.arxiv_id) ?? false}
      onToggleSeen={toggleSeen}
      isTarget={paper.arxiv_id === openId}
      permalink={linkTo(paper)}
      onOpen={onOpenPaper}
      onClose={closePaper}
      onShowInGraph={onShowInGraph}
      citations={citations.get(paper.arxiv_id)}
      citationsNote={citationsNote}
      gain={gainOf?.(paper.arxiv_id)}
      onToggleSaved={toggleSaved}
      onAuthor={onAuthor}
      onAffiliation={onAffiliation}
    />
  );

  let content: ComponentChildren;
  if (withDays) {
    // Each day folds under its heading, open by default. Only the papers of open days
    // count against the paging budget: folding a day pulls the following days up.
    const rendered = [];
    let budget = visible;
    for (const { day, entries } of groups) {
      if (budget <= 0) break;
      const isFolded = folded.has(day);
      rendered.push(
        <details key={day} class="day-group" open={!isFolded}>
          {/* biome-ignore lint/a11y/noStaticElementInteractions: <summary> is natively
              interactive; the rule does not know it. The click is intercepted so that
              folding lives in state, which the paging budget reads. */}
          <summary class="day-heading" onClick={toggleDay(day)}>
            {formatShortDay(day)}
            <span class="day-heading__count">· {countOf(entries.length, "paper")}</span>
          </summary>
          {isFolded ? null : entries.slice(0, budget).map(card)}
        </details>,
      );
      if (!isFolded) budget -= entries.length;
    }
    content = rendered;
  } else {
    content = results.slice(0, visible).map(card);
  }

  return (
    <>
      <div class="paper-list" ref={list}>
        {content}
      </div>
      <div ref={sentinel} aria-hidden="true" />
    </>
  );
}
