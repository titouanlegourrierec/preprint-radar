import { seenHidden } from "../format";
import { arxivIdOf } from "../search";

interface Props {
  /** A shared `?paper=` this period, or the highly cited papers shown, do not hold. */
  missingPaper: string | null;
  /** Said of the highly cited papers, which the archive chooses again every week. */
  missingFromCited?: boolean;
  /** A pasted arXiv id that matches no paper here. */
  missingPastedId: string | null;
  /** The papers are those of a search of every stored paper (PROD-21), not of a period. */
  store?: boolean;
  /** The search of every stored paper, offered from the Papers view's period. */
  onSearchStore?: (() => void) | null;
  /** Papers that Hide seen leaves out of an empty list: the reason it is empty. */
  allSeen: number;
  onShowSeen: () => void;
  /** No paper matches: the remedies it offers, if any. */
  noMatch: {
    /** Said of the Papers view's period. */
    inPeriod: boolean;
    onClearFilters: (() => void) | null;
    /** The longest preset, when it holds more days than the period. */
    wider: { days: number; onSearch: () => void } | null;
  } | null;
}

/** Why a list shows no paper, or not the one asked for, and what to do about it. */
export function NoResults(props: Props) {
  const { missingPaper, missingPastedId, noMatch } = props;
  return (
    <>
      {missingPaper && (
        <p class="notice">
          {props.missingFromCited
            ? "This paper is not among the highly cited papers shown: the archive chooses them again every week."
            : "This paper is not among the stored papers of this period (it may be older than the papers kept)."}
          {/* An arXiv link only for an arXiv id: `?paper=` is anyone's text (SEC-7). */}
          {arxivIdOf(missingPaper) === missingPaper && (
            <>
              {" "}
              <a
                href={`https://arxiv.org/abs/${missingPaper}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                See it on arXiv
              </a>
              .
            </>
          )}
        </p>
      )}
      {missingPastedId && (
        <p class="notice">
          {missingPastedId} is not among the stored papers{props.store ? "" : " of this period"}.{" "}
          {props.onSearchStore && (
            <>
              <button type="button" class="link-button" onClick={props.onSearchStore}>
                Search all stored papers
              </button>
              {" · "}
            </>
          )}
          <a
            href={`https://arxiv.org/abs/${missingPastedId}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            See it on arXiv
          </a>
          .
        </p>
      )}
      {props.allSeen > 0 && (
        <p class="notice" role="status">
          {seenHidden(props.allSeen).empty}{" "}
          <button type="button" class="link-button" onClick={props.onShowSeen}>
            Show seen papers
          </button>
        </p>
      )}
      {noMatch && (
        <p class="notice">
          {props.store ? "No stored paper matches" : "No paper matches"}
          {noMatch.inPeriod ? " in this period" : ""}.{" "}
          {[
            noMatch.onClearFilters && (
              <button
                key="filters"
                type="button"
                class="link-button"
                onClick={noMatch.onClearFilters}
              >
                Clear the filters
              </button>
            ),
            noMatch.wider && (
              <button
                key="wider"
                type="button"
                class="link-button"
                onClick={noMatch.wider.onSearch}
              >
                Search the last {noMatch.wider.days} days
              </button>
            ),
            props.onSearchStore && (
              <button key="store" type="button" class="link-button" onClick={props.onSearchStore}>
                Search all stored papers
              </button>
            ),
          ]
            .filter(Boolean)
            .flatMap((remedy, at) => (at === 0 ? [remedy] : [" · ", remedy]))}
        </p>
      )}
    </>
  );
}
