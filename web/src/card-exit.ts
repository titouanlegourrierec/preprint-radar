/**
 * A card leaving the list as the reader triages it (UX-63): marked seen while seen papers
 * are hidden, or unsaved from the reading list. A copy of it slides out to the right as it
 * fades, and what followed it in sight glides up to its place, rather than the list jumping.
 * The card itself leaves at once, so that the focus and the next key go on (UX-23).
 */

const EXIT_MS = 160;
const CLOSE_MS = 240;
/** What follows waits until the copy has nearly faded, so that their texts never cross. */
const CLOSE_DELAY_MS = 110;
const SHIFT_PX = 40;

/**
 * Note where `card` and what follows it in sight in `scope` are, before the action that may
 * take it out of the list; the function returned, called once the list is drawn again, plays
 * its exit if it left (one that stays, seen but shown, dims by the stylesheet). Nothing
 * under reduced motion.
 */
export function cardExit(
  card: HTMLElement | null | undefined,
  scope: HTMLElement | null | undefined,
): () => void {
  if (!(card && scope) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return () => undefined;
  }
  const rect = card.getBoundingClientRect();
  const copy = card.cloneNode(true) as HTMLElement;
  const followers = [
    ...scope.querySelectorAll<HTMLElement>("article.paper, summary.day-heading, .list-rule"),
  ]
    .filter((element) => card.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING)
    .map((element) => ({ element, top: element.getBoundingClientRect().top }))
    .filter(({ top }) => top < window.innerHeight);
  return () => {
    if (card.isConnected) return;
    // A copy for the eye only: no ids, no focus, out of the accessibility tree.
    for (const element of copy.querySelectorAll("[id]")) element.removeAttribute("id");
    copy.setAttribute("aria-hidden", "true");
    copy.inert = true;
    Object.assign(copy.style, {
      position: "fixed",
      top: `${rect.top}px`,
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      margin: "0",
      zIndex: "3",
      pointerEvents: "none",
    });
    document.body.append(copy);
    const remove = () => copy.remove();
    copy
      .animate(
        [
          { opacity: 1, transform: "none" },
          { opacity: 0, transform: `translateX(${SHIFT_PX}px)` },
        ],
        { duration: EXIT_MS, easing: "ease-out", fill: "forwards" },
      )
      .finished.then(remove, remove);
    for (const { element, top } of followers) {
      if (!element.isConnected) continue;
      // From where it was seen, a former glide cut short.
      for (const animation of element.getAnimations()) animation.cancel();
      const shift = top - element.getBoundingClientRect().top;
      if (Math.abs(shift) < 1) continue;
      element.animate([{ transform: `translateY(${shift}px)` }, { transform: "none" }], {
        duration: CLOSE_MS,
        delay: CLOSE_DELAY_MS,
        easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
        fill: "backwards",
      });
    }
  };
}
