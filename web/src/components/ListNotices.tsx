import type { FeedLink } from "../feeds";
import { countOf } from "../format";
import { PAPER_BUDGET } from "../period";
import type { SearchFilters } from "../search";
import type { ViewState } from "../url-state";
import { ActiveFilters } from "./ActiveFilters";
import { RELEVANCE_HELP } from "./ResultsHeader";

// What each view shows, said once at its top: the tabs' tooltips are out of reach on touch.
const VIEW_NOTES: Partial<Record<ViewState["view"], string>> = {
  cited: "The most cited papers older than a year, by year of first version.",
  rankings: "Institutions and authors of the papers shown, by papers or citations.",
  "reading-list": "The papers you saved with ☆, kept in this browser.",
};

interface Props {
  view: ViewState["view"];
  /** "How is relevance computed?" was asked. */
  relevanceHelp: boolean;
  /** What importing a reading list did, until dismissed. */
  readingListMessage: { text: string; onDismiss: () => void } | null;
  /** New papers since the last visit, out of the period shown. */
  sinceLastVisit: { papers: number; onShow: () => void } | null;
  /** The keys of triage, once the papers are there. */
  shortcuts: boolean;
  /** Archive years past the budget: the papers shown and left out, the years unranked. */
  archiveBudget: { shown: number; leftOut: number; unranked: number } | null;
  /** Where and when the citation counts come from. */
  citationsNote: string | undefined;
  /** Most papers ranked by citations share one count. */
  mostlyTied: boolean;
  /** The filters set, as chips, where the list has them. */
  filters: SearchFilters | null;
  onFilters: (filters: SearchFilters) => void;
  feed: FeedLink | null;
}

/** What a list says above its papers: help, news, notes and the filters set. */
export function ListNotices(props: Props) {
  const { view, archiveBudget } = props;
  return (
    <>
      {props.relevanceHelp && <p class="help-note">{RELEVANCE_HELP}</p>}

      {props.readingListMessage && (
        <p class="notice notice--new" role="status">
          {props.readingListMessage.text}{" "}
          <button type="button" class="link-button" onClick={props.readingListMessage.onDismiss}>
            Dismiss
          </button>
        </p>
      )}

      {props.sinceLastVisit && (
        <p class="notice notice--new">
          {countOf(props.sinceLastVisit.papers, "new paper")} since your last visit.{" "}
          <button type="button" class="link-button" onClick={props.sinceLastVisit.onShow}>
            {props.sinceLastVisit.papers > PAPER_BUDGET
              ? `Show the latest ${PAPER_BUDGET.toLocaleString()}`
              : "Show them"}
          </button>
        </p>
      )}
      {props.shortcuts && (
        <p class="shortcuts muted">
          Keys: <kbd>j</kbd> <kbd>k</kbd> move, <kbd>o</kbd> open, <kbd>s</kbd> save, <kbd>x</kbd>{" "}
          seen, <kbd>/</kbd> search, <kbd>Esc</kbd> leave the search.
        </p>
      )}

      {archiveBudget && (
        <p class="help-note">
          These years hold {(archiveBudget.shown + archiveBudget.leftOut).toLocaleString()} papers:
          the {archiveBudget.shown.toLocaleString()} best ranked by citations per year of age are
          shown, as many as a period loads. Narrow the years for the{" "}
          {archiveBudget.leftOut.toLocaleString()} others.
          {archiveBudget.unranked > 0 &&
            ` The citation counts of ${countOf(archiveBudget.unranked, "year")} could not be loaded: their papers rank last, so most are among those left out.`}
        </p>
      )}
      {VIEW_NOTES[view] && (
        <p class="view-note muted">
          {VIEW_NOTES[view]}
          {view === "cited" &&
            ` Chosen every week by citations per year of age, among the papers first published more than 12 months ago.${props.citationsNote ? ` ${props.citationsNote}.` : ""}`}
        </p>
      )}
      {props.mostlyTied && (
        <p class="help-note">
          Most of these papers have the same number of citations (often none yet, or not known):
          among them, the order is by relevance or date.
        </p>
      )}
      {props.filters && <ActiveFilters filters={props.filters} onFilters={props.onFilters} />}
      {props.feed && (
        <p class="feed-link muted">
          New papers {props.feed.kind === "venue" ? "accepted at" : "from"} {props.feed.name}, in a
          feed reader:{" "}
          <a href={encodeURI(props.feed.path)} type="application/atom+xml">
            Atom feed
          </a>
        </p>
      )}
    </>
  );
}
