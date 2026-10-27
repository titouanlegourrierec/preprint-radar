import type { Ref } from "preact";
import { useState } from "preact/hooks";
import { countOf, DATED_BY_MONTH, datedByMonth, formatAnnounced } from "../format";
import {
  type Connection,
  type EntityKind,
  type EntityNode,
  type GraphOptions,
  linkPapers,
  severalPeople,
} from "../graph";
import type { Paper } from "../types";

const DETAILS_PAPERS = 8;
const DETAILS_AUTHORS = 8;
const KIND_NAMES = { paper: "Paper", institution: "Institution", author: "Author" } as const;

/** Paper ids, most cited first; unknown counts last, and ties keep their order. */
function byCitationCount(ids: readonly string[], citations: ReadonlyMap<string, number>): string[] {
  return [...ids].sort((a, b) => (citations.get(b) ?? -1) - (citations.get(a) ?? -1));
}

interface Props {
  /** The entity selected, or `null` for a paper. */
  entity: EntityNode | null;
  /** The paper selected, a node or not (no institution or author to link it to). */
  paper: Paper | undefined;
  /** Why the selected paper has no node, if it has none. */
  absent: string | null;
  /** The entity's most connected nodes (`nodeConnections`). */
  connections: Connection[];
  papersById: ReadonlyMap<string, Paper>;
  /** The graph's options, which say which papers a connection counts (`linkPapers`). */
  options: GraphOptions;
  citations: ReadonlyMap<string, number>;
  /** The oldest day file: older papers are dated by their month (META-5). */
  oldestDay: string | undefined;
  focus: string | null;
  detailsRef: Ref<HTMLElement>;
  onClose: () => void;
  onSelect: (id: string) => void;
  onShowPapers: (kind: EntityKind, label: string) => void;
  onFocus: (id: string) => void;
  onOpenPaper: (paper: Paper) => void;
  /**
   * Point at a node of the canvas from a row hovered or focused (UX-61), its id, or `null`
   * once left.
   */
  onPeek: (id: string | null) => void;
}

/** A row's handlers that point at its node on the canvas while hovered or focused (UX-61). */
function peeking(id: string, onPeek: (id: string | null) => void) {
  return {
    onPointerEnter: () => onPeek(id),
    onPointerLeave: () => onPeek(null),
    onFocusIn: () => onPeek(id),
    onFocusOut: () => onPeek(null),
  };
}

/** The details of the node selected: a paper, or an institution or author and its papers. */
export function GraphDetails(props: Props) {
  const { entity, paper, citations } = props;
  return (
    <aside class="graph__details" aria-label="Details" ref={props.detailsRef} tabIndex={-1}>
      <button type="button" class="graph__close" aria-label="Close" onClick={props.onClose}>
        ×
      </button>
      <p class="graph__kind">{KIND_NAMES[entity?.kind ?? "paper"]}</p>
      {paper ? (
        <PaperDetails
          paper={paper}
          absent={props.absent}
          citations={citations.get(paper.arxiv_id)}
          oldestDay={props.oldestDay}
          onOpen={() => props.onOpenPaper(paper)}
        />
      ) : (
        entity && (
          // Another entity's details start with its connections folded.
          <EntityDetails key={entity.id} {...props} entity={entity} />
        )
      )}
    </aside>
  );
}

function EntityDetails(props: Props & { entity: EntityNode }) {
  const { entity, citations, papersById } = props;
  // The connection whose shared papers are listed.
  const [open, setOpen] = useState<string | null>(null);
  const strongest = Math.max(1, ...props.connections.map(({ weight }) => weight));
  return (
    <>
      <h2>{entity.label}</h2>
      <p
        class="muted graph__counts"
        title="Over the papers shown: the period or year, and the search"
      >
        {countOf(entity.paperIds.length, "paper")} · {countOf(entity.citations, "citation")}
        {entity.rorId && (
          <>
            {" · "}
            <a
              href={`https://ror.org/${entity.rorId}`}
              title="This institution in the Research Organization Registry"
              target="_blank"
              rel="noopener noreferrer"
            >
              ROR
            </a>
          </>
        )}
      </p>
      {entity.people && <p class="muted">{severalPeople(entity.people)}</p>}
      <ul class="graph__papers">
        {byCitationCount(entity.paperIds, citations)
          .slice(0, DETAILS_PAPERS)
          .map((id) => {
            const paper = papersById.get(id);
            const count = citations.get(id);
            return paper ? (
              <li key={id} {...peeking(`paper:${id}`, props.onPeek)}>
                <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
                  {paper.title}
                </a>{" "}
                <span class="muted">
                  · {formatAnnounced(paper.announced, props.oldestDay)}
                  {count !== undefined && ` · ${countOf(count, "citation")}`}
                </span>
              </li>
            ) : null;
          })}
      </ul>
      {props.connections.length > 0 && (
        <>
          <p class="graph__kind">Most connected</p>
          <ul class="graph__connections">
            {props.connections.map(({ node, weight }) => (
              // Its name and count side by side, over a bar of its share of the strongest's.
              <li
                key={node.id}
                class="graph__connection"
                style={`--weight: ${(weight / strongest).toFixed(3)}`}
                {...peeking(node.id, props.onPeek)}
              >
                <button type="button" class="link-button" onClick={() => props.onSelect(node.id)}>
                  {node.label}
                </button>{" "}
                <button
                  type="button"
                  class="link-button muted"
                  aria-expanded={open === node.id}
                  title="The papers they share"
                  onClick={() => setOpen(open === node.id ? null : node.id)}
                >
                  {countOf(weight, "shared paper")}
                </button>
                {open === node.id && (
                  <ul class="graph__shared">
                    {byCitationCount(
                      linkPapers(entity, node, papersById, props.options),
                      citations,
                    ).map((id) => {
                      const paper = papersById.get(id);
                      return paper ? (
                        <li key={id}>
                          <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
                            {paper.title}
                          </a>
                        </li>
                      ) : null;
                    })}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <div class="graph__actions">
        <button
          type="button"
          class="button"
          onClick={() => props.onShowPapers(entity.kind, entity.label)}
        >
          {entity.paperIds.length === 1
            ? "Show its paper"
            : `Show all ${countOf(entity.paperIds.length, "paper")}`}
        </button>
        {props.focus !== entity.id && (
          <button
            type="button"
            class="button"
            title="The graph of its papers alone: with whom it publishes"
            onClick={() => props.onFocus(entity.id)}
          >
            Focus on this
          </button>
        )}
      </div>
    </>
  );
}

/** Details of a selected paper: what it is, who wrote it, where, and a way to read it. */
function PaperDetails({
  paper,
  absent,
  citations,
  oldestDay,
  onOpen,
}: {
  paper: Paper;
  /** Why the paper has no node, if it has none. */
  absent: string | null;
  /** Its citation count, when known. */
  citations: number | undefined;
  oldestDay: string | undefined;
  onOpen: () => void;
}) {
  const authors = paper.authors.slice(0, DETAILS_AUTHORS).join(", ");
  const hidden = paper.authors.length - DETAILS_AUTHORS;
  return (
    <>
      <h2>
        <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
          {paper.title}
        </a>
      </h2>
      <p class="muted">
        <span title={datedByMonth(paper.announced, oldestDay) ? DATED_BY_MONTH : undefined}>
          {formatAnnounced(paper.announced, oldestDay)}
        </span>
        {paper.venue && ` · ${paper.venue}`}
        {citations !== undefined && ` · ${countOf(citations, "citation")}`}
      </p>
      <p>
        {authors}
        {hidden > 0 && <span class="muted"> +{hidden}</span>}
      </p>
      {(paper.affiliations ?? []).length > 0 && (
        <ul class="graph__connections">
          {(paper.affiliations ?? []).map((affiliation) => (
            <li key={affiliation}>{affiliation}</li>
          ))}
        </ul>
      )}
      {absent && <p class="muted">{absent}</p>}
      <button type="button" class="button" onClick={onOpen}>
        Open in the list
      </button>
    </>
  );
}
