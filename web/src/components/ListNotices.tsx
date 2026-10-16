import { useMemo } from "preact/hooks";
import type { FeedLink } from "../feeds";
import { affiliationCoverage, countOf } from "../format";
import { formatMissingDays, PAPER_BUDGET } from "../period";
import type { SearchFilters } from "../search";
import type { Paper } from "../types";
import type { ViewState } from "../url-state";
import { ActiveFilters } from "./ActiveFilters";
import { InfoButton } from "./InfoButton";

// What each view shows, in its ⓘ: the tabs' tooltips are out of reach on touch.
const VIEW_NOTES: Partial<Record<ViewState["view"], string>> = {
  cited: "The most cited papers older than a year, by year of first version.",
  rankings: "Institutions and authors of the papers shown, by papers or citations.",
  "reading-list": "The papers you saved from the star of their card, kept in this browser.",
};

// How the highly cited papers are chosen, after the note: by the archive, or apart from it.
const ARCHIVE_RULE =
  "Chosen every week by citations per year of age, among the papers first published more than 12 months ago.";
const RECENT_NOTE = "The most cited papers of the last 12 months.";
const RECENT_RULE =
  "Chosen every week by citations per month of age, counted over two months at least, so that each month has its best papers.";

interface NotesProps {
  view: ViewState["view"];
  /** The papers shown, whose affiliations are counted. */
  papers: readonly Paper[];
  /** Where and when the citation counts come from. */
  citationsNote: string | undefined;
  /** The papers are highly cited ones, which have citations. */
  archived: boolean;
  /** The highly cited view shows the most cited papers of the last 12 months. */
  lastMonths: boolean;
}

/**
 * What a list says of its papers, behind the ⓘ beside its count (UX-33), as the graph's
 * does: what the view shows and how its papers are chosen, how many have known
 * affiliations, and the citation counts' date. No ⓘ while it would say nothing.
 */
export function ViewNotes({ view, papers, citationsNote, archived, lastMonths }: NotesProps) {
  const note = view === "cited" && lastMonths ? RECENT_NOTE : VIEW_NOTES[view];
  const affiliated = useMemo(
    () => papers.filter((paper) => (paper.affiliations ?? []).length > 0).length,
    [papers],
  );
  if (!(note || citationsNote || papers.length > 0)) return null;
  return (
    <InfoButton label="About these papers">
      {note && (
        <p>
          {note}
          {view === "cited" && ` ${lastMonths ? RECENT_RULE : ARCHIVE_RULE}`}
        </p>
      )}
      {view === "rankings" && (
        <p>
          Citations are summed over their papers{archived ? "" : ": recent papers have few yet"}.
        </p>
      )}
      {papers.length > 0 && <p>{`${affiliationCoverage(affiliated, papers.length)}.`}</p>}
      {citationsNote && <p>{`${citationsNote}.`}</p>}
    </InfoButton>
  );
}

interface Props {
  /** What importing a reading list did, until dismissed. */
  readingListMessage: { text: string; onDismiss: () => void } | null;
  /** New papers since the last visit, out of the period shown. */
  sinceLastVisit: { papers: number; onShow: () => void } | null;
  /** Days of the period whose day file or search shard did not load, not shown. */
  missingDays: { days: string[]; onRetry: () => void } | null;
  /** Archive years past the budget: the papers shown and left out, the years unranked. */
  archiveBudget: { shown: number; leftOut: number; unranked: number } | null;
  /** The citation counts' note, when they are old enough to say so above the papers. */
  staleCitations: string | null;
  /** Most papers ranked by citations share one count. */
  mostlyTied: boolean;
  /** The filters set, as chips, where the list has them. */
  filters: SearchFilters | null;
  onFilters: (filters: SearchFilters) => void;
  feed: FeedLink | null;
}

/** What a list says above its papers: news, warnings and the filters set. */
export function ListNotices(props: Props) {
  const { archiveBudget } = props;
  return (
    <>
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

      {props.missingDays && (
        <p class="notice notice--error" role="alert">
          The papers of {formatMissingDays(props.missingDays.days)} could not be loaded: they are
          not shown.{" "}
          <button type="button" class="link-button" onClick={props.missingDays.onRetry}>
            Retry
          </button>
        </p>
      )}
      {archiveBudget && (
        <p class="help-note">
          These years hold {(archiveBudget.shown + archiveBudget.leftOut).toLocaleString()} papers:
          the {archiveBudget.shown.toLocaleString()} best ranked by citations per year of age are
          shown, as many as a period loads. Narrow the years for the{" "}
          {archiveBudget.leftOut.toLocaleString()} others.
          {archiveBudget.unranked > 0 &&
            ` The citation counts of ${countOf(archiveBudget.unranked, "year")} could not be loaded: their papers rank last, the first to be left out.`}
        </p>
      )}
      {props.staleCitations && <p class="help-note">{`${props.staleCitations}.`}</p>}
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
