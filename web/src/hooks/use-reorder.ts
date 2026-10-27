import type { RefObject } from "preact";
import { useLayoutEffect, useMemo, useRef } from "preact/hooks";
import { rankMoves } from "../moves";

let lists = 0;

/** A name for a list of rows: another for other papers, or another kind of row (UX-62). */
export function useListId(papers: readonly unknown[], kind: string): string {
  return useMemo(() => `${kind} ${++lists}`, [papers, kind]);
}

/** How long a row glides to its new place (UX-62). */
const GLIDE_MS = 420;

interface Drawn {
  keys: readonly string[];
  order: string;
  list: string;
  /** Each row's offset in its parent, as last laid out. */
  offsets: ReadonlyMap<string, number>;
}

/**
 * Rows that glide from their former place to their new one when the reader ranks them
 * otherwise (UX-62, FLIP): the rows (`[data-key]` in `container`) note their offsets after
 * each layout; when `order` changes but not `list`, those in sight that moved animate from
 * their former offset, newcomers fade in. Another list (a period, a search) only redraws.
 * Returns each row's move of the last reordering, kept until another list.
 */
export function useReorder(
  container: RefObject<HTMLElement | null>,
  keys: readonly string[],
  order: string,
  list: string,
): ReadonlyMap<string, number | null> | null {
  const drawn = useRef<Drawn | null>(null);
  const moves = useRef<{ list: string; moves: ReadonlyMap<string, number | null> } | null>(null);
  // Read as this render draws the new order, before its layout notes it.
  const before = drawn.current;
  if (before && before.order !== order && before.list === list) {
    moves.current = { list, moves: rankMoves(before.keys, keys) };
  } else if (moves.current && moves.current.list !== list) {
    moves.current = null;
  }

  const keyed = keys.join(" ");
  useLayoutEffect(() => {
    const root = container.current;
    if (!root) return;
    const rows = [...root.querySelectorAll<HTMLElement>("[data-key]")];
    const offsets = new Map(rows.map((row) => [row.dataset.key ?? "", row.offsetTop]));
    const previous = drawn.current;
    drawn.current = { keys, order, list, offsets };
    if (!previous || previous.order === order || previous.list !== list) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const top = root.getBoundingClientRect().top;
    for (const row of rows) {
      const now = offsets.get(row.dataset.key ?? "") ?? 0;
      // Those in sight, a screen either way.
      if (top + now < -window.innerHeight || top + now > 2 * window.innerHeight) continue;
      const was = previous.offsets.get(row.dataset.key ?? "");
      for (const animation of row.getAnimations()) animation.cancel();
      if (was === undefined) {
        row.animate([{ opacity: 0 }, { opacity: 1 }], { duration: GLIDE_MS, easing: "ease" });
      } else if (was !== now) {
        row.animate([{ transform: `translateY(${was - now}px)` }, { transform: "none" }], {
          duration: GLIDE_MS,
          easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
        });
      }
    }
  }, [keyed, order, list]);
  return moves.current?.moves ?? null;
}
