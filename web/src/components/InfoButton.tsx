import type { ComponentChildren } from "preact";
import { useCallback, useId, useRef, useState } from "preact/hooks";
import { useDismiss } from "../hooks/use-dismiss";

interface Props {
  /** What the button opens, its name for screen readers and its tooltip. */
  label: string;
  /** The notes, as paragraphs. */
  children: ComponentChildren;
  /** Where the notes open: under the button (the lists), or above it (the graph's corner). */
  above?: boolean | undefined;
  /** Which edge of the button the notes line up with; the right one near the window's. */
  end?: boolean | undefined;
  class?: string | undefined;
}

/**
 * An ⓘ button and the notes it opens (UX-29, UX-33): what a view says of its data, shown
 * on demand rather than above the papers. A click elsewhere or Escape closes them.
 */
export function InfoButton({ label, children, above, end, class: className }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const close = useCallback((escaped: boolean) => {
    setOpen(false);
    if (escaped) buttonRef.current?.focus();
  }, []);
  useDismiss(open, rootRef, close);

  return (
    <div class={`info${className ? ` ${className}` : ""}`} ref={rootRef}>
      <button
        type="button"
        class="info__button"
        ref={buttonRef}
        aria-label={label}
        title={label}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true">i</span>
      </button>
      {open && (
        <div
          class={`info__panel${above ? " info__panel--above" : ""}${end ? " info__panel--end" : ""}`}
          id={panelId}
        >
          {children}
        </div>
      )}
    </div>
  );
}
