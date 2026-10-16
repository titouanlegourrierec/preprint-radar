import type { Ref } from "preact";
import { useState } from "preact/hooks";
import { type GraphNode, matchStatus } from "../graph";

interface Props {
  value: string;
  input: Ref<HTMLInputElement>;
  onChange: (text: string) => void;
  /** The first matches, listed under the field. */
  matches: GraphNode[];
  /** How many nodes match in all. */
  matchCount: number;
  /** The match shown last, `null` before one is, and its name. */
  matchIndex: number | null;
  matchLabel: string | null;
  /** Show the next match (1) or the previous one (-1). */
  onCycle: (step: 1 | -1) => void;
  /** Show the match at this index of `matches`, and move the focus to its details. */
  onChoose: (index: number) => void;
  /** Filter the papers to these words instead ("Only show papers matching…"). */
  onFilter: (text: string) => void;
}

/**
 * The field that finds a node by name, at the top left of the canvas, above the details of
 * the node it shows (UX-29): a combobox whose first matches are listed under it, all of
 * them highlighted, and Enter or Shift+Enter going from one to the next.
 */
export function GraphFind(props: Props) {
  // The listed match the arrow keys point at, and whether the list shows (field focused).
  const [active, setActive] = useState<number | null>(null);
  const [listing, setListing] = useState(false);
  const listed = listing && props.value.trim() !== "" && props.matches.length > 0;

  return (
    <div class="graph-find">
      <svg
        class="graph-find__icon"
        width="15"
        height="15"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
      >
        <circle cx="7" cy="7" r="4.6" stroke="currentColor" />
        <path d="M10.4 10.4L14 14" stroke="currentColor" stroke-linecap="round" />
      </svg>
      <input
        ref={props.input}
        type="search"
        /* biome-ignore lint/a11y/noRedundantRoles: the field has no list (`list={undefined}`
           only meets Preact 11's types, which want one for a combobox on a search field), so
           its role is not implied; ARIA in HTML allows it, its matches being its listbox. */
        role="combobox"
        list={undefined}
        placeholder="Find a node…"
        aria-label="Find a node by name"
        aria-keyshortcuts="/"
        aria-autocomplete="list"
        aria-expanded={listed}
        aria-controls="graph-matches"
        aria-activedescendant={listed && active !== null ? `graph-match-${active}` : undefined}
        value={props.value}
        onInput={(event) => {
          setActive(null);
          props.onChange(event.currentTarget.value);
        }}
        onFocus={() => setListing(true)}
        onBlur={() => {
          setListing(false);
          setActive(null);
        }}
        onKeyDown={(event) => {
          const last = props.matches.length - 1;
          if (event.key === "ArrowDown" && listed) {
            event.preventDefault();
            setActive(active === null || active >= last ? 0 : active + 1);
          } else if (event.key === "ArrowUp" && listed) {
            event.preventDefault();
            setActive(active === null || active <= 0 ? last : active - 1);
          } else if (event.key === "Enter" && active !== null && listed) {
            event.preventDefault();
            props.onChoose(active);
          } else if (event.key === "Enter") {
            event.preventDefault();
            props.onCycle(event.shiftKey ? -1 : 1);
          }
        }}
      />
      {props.value === "" && (
        <span class="graph-find__key" aria-hidden="true">
          /
        </span>
      )}
      {listing && props.value.trim() !== "" && (
        <div class="graph-find__drop">
          {listed && (
            <div id="graph-matches" class="graph-find__matches" role="listbox" aria-label="Matches">
              {props.matches.map((node, index) => (
                <div
                  key={node.id}
                  id={`graph-match-${index}`}
                  role="option"
                  tabIndex={-1}
                  aria-selected={index === active}
                  class={index === active ? "is-active" : undefined}
                  // Chosen before the field loses the focus, which would close the list.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    props.onChoose(index);
                  }}
                >
                  <i class={`graph__dot graph__dot--${node.kind}`} aria-hidden="true" />
                  {node.label}
                </div>
              ))}
            </div>
          )}
          <button
            type="button"
            class="graph-find__filter"
            // Chosen before the field loses the focus, which would close the list.
            onMouseDown={(event) => {
              event.preventDefault();
              props.onFilter(props.value.trim());
            }}
          >
            Only show papers matching “{props.value.trim()}”
          </button>
        </div>
      )}
      {props.value.trim() !== "" && (
        <p class="graph-find__status" role="status">
          {matchStatus(props.matchCount, props.matchIndex, props.matchLabel)}
        </p>
      )}
    </div>
  );
}
