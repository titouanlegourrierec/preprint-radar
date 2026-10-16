import type { RefObject } from "preact";
import { useEffect } from "preact/hooks";

/**
 * Closes a disclosure (a chip's panel, the calendar, an ⓘ note) on a click outside its
 * root, or on Escape, which goes no further: it does not also leave the search or deselect
 * the graph's node. Tab is free to leave it, so there is no focus trap.
 */
export function useDismiss(
  open: boolean,
  root: RefObject<HTMLElement>,
  onClose: (escaped: boolean) => void,
): void {
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) onClose(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      onClose(true);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, root, onClose]);
}
