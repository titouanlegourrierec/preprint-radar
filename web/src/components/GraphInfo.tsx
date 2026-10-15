import { useEffect, useId, useRef, useState } from "preact/hooks";
import { affiliationCoverage } from "../format";
import { Attribution } from "./Attribution";

interface Props {
  /** The papers drawn, and those of them whose affiliations are known. */
  affiliated: number;
  total: number;
  /** "paper", or "matching paper" when words filter the graph. */
  noun: string;
  /** Where the citation counts come from and their date, for the sources line (REL-10). */
  citationsNote: string | undefined;
}

/**
 * The ⓘ button beside the legend: the notes on the data, shown on demand (UX-29) — how
 * many of the papers drawn have known affiliations (the others count for no institution,
 * PROD-16), the attribution, and the citation counts' date.
 */
export function GraphInfo({ affiliated, total, noun, citationsNote }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  // A click elsewhere or Escape closes it, like the period picker's calendar; Escape stays
  // here, not also deselecting the graph's node.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div class="graph-info" ref={rootRef}>
      {open && (
        <div class="graph-info__panel" id={panelId}>
          <p>{`${affiliationCoverage(affiliated, total, noun)}.`}</p>
          <p>
            <Attribution />
            {citationsNote && ` ${citationsNote}.`}
          </p>
        </div>
      )}
      <button
        type="button"
        class="graph-info__button"
        aria-label="About the data"
        title="About the data"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true">i</span>
      </button>
    </div>
  );
}
