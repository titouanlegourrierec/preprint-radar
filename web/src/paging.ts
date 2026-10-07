/**
 * The list's paging (`components/PaperList.tsx`): cards are added a page at a time as the
 * end of the list comes into view. A new list starts over at one page; the same list, whose
 * cards change because one was marked seen or unsaved, or because citation counts came
 * and ranked it, keeps the cards shown (UX-23).
 */

/** Cards added at a time. */
export const PAGE_SIZE = 40;

/**
 * Cards to show: one page for a new list, those shown for the same one, and always enough
 * to reach a shared link's target (`targetIndex`, -1 for none).
 */
export function pageCount({
  keyChanged,
  visible,
  targetIndex,
}: {
  keyChanged: boolean;
  visible: number;
  targetIndex: number;
}): number {
  const reach = Math.ceil((targetIndex + 1) / PAGE_SIZE) * PAGE_SIZE;
  return Math.max(keyChanged ? PAGE_SIZE : visible, PAGE_SIZE, reach);
}

/**
 * Cards to show once the end of the list comes into view: a page more while some are left.
 * An empty list (loading) or one shown whole, whose end is always in view, does not grow.
 */
export function nextPage(visible: number, total: number): number {
  return visible < total ? visible + PAGE_SIZE : visible;
}

/**
 * The card to focus once the focused one at `index` left the list (marked seen while seen
 * papers are hidden, unsaved from the reading list): the one now at its place, else the
 * last; -1 when none is left.
 */
export function nextFocusIndex(cards: number, index: number): number {
  return cards === 0 ? -1 : Math.min(Math.max(index, 0), cards - 1);
}
