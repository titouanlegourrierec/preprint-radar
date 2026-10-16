import { useCallback, useRef, useState } from "preact/hooks";
import { useDismiss } from "../hooks/use-dismiss";
import { ChevronIcon, FolderIcon } from "./icons";

interface Props {
  /** Every folder of the reading list, in its order. */
  names: readonly string[];
  /** Those holding the paper. */
  holding: readonly string[];
  onChange: (name: string, inFolder: boolean) => void;
  /** The card's title, which names its paper for screen readers. */
  describedBy: string;
}

/**
 * A card's folders in the reading list (UX-45): a badge naming them, which opens a box to
 * check for each folder, a paper being in as many as one likes. Escape or a click outside
 * closes it.
 */
export function FolderMenu({ names, holding, onChange, describedBy }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const close = useCallback((escaped: boolean) => {
    setOpen(false);
    if (escaped) toggle.current?.focus();
  }, []);
  useDismiss(open, root, close);
  const [first] = holding;
  const label =
    first === undefined ? "Folder" : holding.length === 1 ? first : `${holding.length} folders`;
  return (
    <div class="folder-menu" ref={root}>
      <button
        ref={toggle}
        type="button"
        class="action"
        aria-expanded={open}
        aria-describedby={describedBy}
        title={holding.length > 1 ? holding.join(" · ") : "Its folders in the reading list"}
        onClick={() => setOpen(!open)}
      >
        <FolderIcon />
        <span class="folder-menu__label">{label}</span>
        <ChevronIcon up={open} />
      </button>
      {open && (
        <fieldset class="folder-menu__panel">
          <legend class="visually-hidden">Its folders</legend>
          {names.map((name) => (
            <label key={name} class="folder-menu__option">
              <input
                type="checkbox"
                checked={holding.includes(name)}
                onChange={(event) => onChange(name, event.currentTarget.checked)}
              />
              <span>{name}</span>
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );
}
