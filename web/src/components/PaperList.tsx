import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { dayGroups } from "../day-groups";
import { countOf, formatShortDay } from "../format";
import { hasModifier, isTyping } from "../keyboard";
import { nextFocusIndex, nextPage, PAGE_SIZE, pageCount } from "../paging";
import type { NameFilter, NameHighlights, SearchResult } from "../search";
import type { Paper } from "../types";
import { ChevronIcon } from "./icons";
import { PaperCard } from "./PaperCard";

interface Props {
  results: SearchResult[];
  /** What makes a new list (`listKey`): its paging starts over only when this changes. */
  resetKey: string;
  /** The names filtered on, which cards mark in their author and affiliation lines. */
  nameHighlights: NameHighlights;
  /** Insert a heading before each day; needs results in announcement order. */
  groupByDay: boolean;
  /** Each card says its rank in the order shown (UX-36); never with day headings. */
  ranked: boolean;
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
  /**
   * Move a paper before or after another, in the reading list's own order (UX-39): by
   * dragging its card, or Alt+arrows on it; absent in any other order.
   */
  onMove?: ((arxivId: string, target: string, place: "before" | "after") => void) | undefined;
  /** The reading list's folders, each card's select putting its paper in one (UX-38). */
  folders?:
    | {
        names: string[];
        of: (arxivId: string) => string | null;
        onPut: (arxivId: string, name: string | null) => void;
      }
    | undefined;
}

/** Render results incrementally: the next page is added when the end of the list is visible. */
export function PaperList({
  results,
  resetKey,
  nameHighlights,
  groupByDay,
  ranked,
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
  onMove,
  folders,
}: Props) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  // The card dragged by its handle, and where it would go among the others (UX-39).
  const [dragged, setDragged] = useState<string | null>(null);
  const [drop, setDrop] = useState<{ id: string; place: "before" | "after" } | null>(null);
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
  const order = useMemo(() => results.map(({ paper }) => paper.arxiv_id), [results]);
  const actions = useRef({ byId, onToggleSaved, onToggleSeen, onMove, order });
  actions.current = { byId, onToggleSaved, onToggleSeen, onMove, order };
  // The results' count, for the observer that adds pages, set up once.
  const total = useRef(results.length);
  total.current = results.length;
  useEffect(() => {
    // Alt+arrows move the focused card in the reading list's own order (UX-39), as a drag.
    const moveFocused = (event: KeyboardEvent): boolean => {
      const { onMove, order } = actions.current;
      const card = document.activeElement;
      const up = event.key === "ArrowUp";
      if (!(onMove && card instanceof HTMLElement && card.matches("article.paper"))) return false;
      const id = card.dataset.arxivId ?? "";
      const index = order.indexOf(id);
      const neighbour = order[index + (up ? -1 : 1)];
      if (index === -1 || neighbour === undefined) return false;
      onMove(id, neighbour, up ? "before" : "after");
      // Moved in the page, the card can lose the focus: it takes it back once drawn.
      setTimeout(() => {
        const moved = list.current?.querySelector<HTMLElement>(
          `article.paper[data-arxiv-id="${CSS.escape(id)}"]`,
        );
        moved?.focus();
        moved?.scrollIntoView({ block: "nearest" });
      }, 0);
      return true;
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.altKey &&
        !event.metaKey &&
        !event.ctrlKey &&
        (event.key === "ArrowUp" || event.key === "ArrowDown") &&
        !event.defaultPrevented &&
        moveFocused(event)
      ) {
        event.preventDefault();
        return;
      }
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

  const card = ({ paper, highlights }: SearchResult, rank?: number) => (
    <PaperCard
      key={paper.arxiv_id}
      paper={paper}
      rank={rank}
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
      drag={
        folders
          ? {
              dragging: dragged === paper.arxiv_id,
              drop: drop?.id === paper.arxiv_id ? drop.place : null,
              onStart: setDragged,
              onEnd: () => {
                setDragged(null);
                setDrop(null);
              },
            }
          : undefined
      }
      folder={
        folders && folders.names.length > 0
          ? {
              name: folders.of(paper.arxiv_id),
              names: folders.names,
              onChange: (name) => folders.onPut(paper.arxiv_id, name),
            }
          : undefined
      }
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
            {/* Down while open, turned to the right while folded (styles.css). */}
            <span class="day-heading__fold">
              <ChevronIcon up={false} />
            </span>
            {formatShortDay(day)}
            <span class="day-heading__count">· {countOf(entries.length, "paper")}</span>
          </summary>
          {isFolded ? null : entries.slice(0, budget).map((entry) => card(entry))}
        </details>,
      );
      if (!isFolded) budget -= entries.length;
    }
    content = rendered;
  } else {
    content = results
      .slice(0, visible)
      .map((result, index) => card(result, ranked ? index + 1 : undefined));
  }

  return (
    <>
      {/* biome-ignore lint/a11y/noStaticElementInteractions: where a dragged card lands, for
          the pointer; the keyboard moves the focused card with Alt+arrows (above). */}
      <div
        class={dragged ? "paper-list paper-list--dragging" : "paper-list"}
        ref={list}
        // A card dragged over another goes before or after it, as the pointer is over its
        // top or bottom half; in the reading list's own order only (UX-39).
        onDragOver={(event) => {
          if (!onMove || dragged === null || !(event.target instanceof Element)) return;
          const card = event.target.closest<HTMLElement>("article.paper");
          const id = card?.dataset.arxivId;
          if (!card || !id || id === dragged) {
            if (drop) setDrop(null);
            return;
          }
          event.preventDefault();
          if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
          const box = card.getBoundingClientRect();
          const place = event.clientY < box.top + box.height / 2 ? "before" : "after";
          if (drop?.id !== id || drop.place !== place) setDrop({ id, place });
        }}
        onDragLeave={(event) => {
          if (!(event.relatedTarget instanceof Node && list.current?.contains(event.relatedTarget)))
            setDrop(null);
        }}
        onDrop={(event) => {
          if (!onMove || dragged === null || drop === null) return;
          event.preventDefault();
          onMove(dragged, drop.id, drop.place);
          setDrop(null);
        }}
      >
        {content}
      </div>
      <div ref={sentinel} aria-hidden="true" />
    </>
  );
}
