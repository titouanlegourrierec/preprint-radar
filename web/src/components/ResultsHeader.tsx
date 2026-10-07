import { useRef } from "preact/hooks";
import { toBibtexFile } from "../bibtex";
import { download } from "../download";
import { toCsv, toMarkdown, toRis } from "../export";
import { countOf, formatDay } from "../format";
import type { Paper } from "../types";
import type { CountLine, SortChoice, ViewModel } from "../view-model";

// The exports of the results shown, as files.
const EXPORTS: {
  label: string;
  file: string;
  type: string;
  render: (papers: Paper[], citations: ReadonlyMap<string, number>) => string;
}[] = [
  {
    label: "BibTeX",
    file: "papers.bib",
    type: "application/x-bibtex",
    render: (papers) => toBibtexFile(papers),
  },
  { label: "CSV", file: "papers.csv", type: "text/csv", render: toCsv },
  {
    label: "RIS",
    file: "papers.ris",
    type: "application/x-research-info-systems",
    render: (papers) => toRis(papers),
  },
  {
    label: "Markdown",
    file: "papers.md",
    type: "text/markdown",
    render: (papers) => toMarkdown(papers),
  },
];

export const RELEVANCE_HELP =
  "Relevance ranks papers by how well they match your search words. Rarer words weigh more, " +
  "and a match counts most in the title, then in authors, affiliations, the abstract and " +
  "comments. Exact words count more than partial or approximate ones.";

const SORT_LABELS: Record<SortChoice, string> = {
  relevance: "Relevance",
  newest: "Newest",
  citations: "Most cited",
  rising: "Rising",
};

interface Props {
  model: ViewModel;
  /** What the header counts; `null` while there is nothing to count. */
  count: CountLine | "loading" | null;
  onSort: (sort: SortChoice) => void;
  /** Where the counts come from, for Most cited's tooltip. */
  citationsNote: string | undefined;
  /** The days Rising's gains span, for its tooltip. */
  gainsSpan: { since: string; to: string } | null;
  relevanceHelpShown: boolean;
  onRelevanceHelp: () => void;
  hideSeen: boolean;
  onHideSeen: () => void;
  showAbstracts: boolean;
  onShowAbstracts: () => void;
  /** The papers shown, for the Export menu, with their citation counts. */
  papers: Paper[];
  citations: ReadonlyMap<string, number>;
  /** The reading list's own tools, in its view. */
  readingList?:
    | {
        papers: Paper[];
        onImport: (file: File) => void;
        /** The list as a JSON file, its saved searches with it. */
        json: () => string;
      }
    | undefined;
}

function countText(count: CountLine): string {
  return `${count.shown.toLocaleString()} of ${countOf(count.total, count.noun)}${count.tail ?? ""}`;
}

/**
 * The top of a list: how many papers it shows, its order, its toggles, and what it can
 * export or import.
 */
export function ResultsHeader(props: Props) {
  const { model, count } = props;
  const importInput = useRef<HTMLInputElement>(null);
  const titles: Partial<Record<SortChoice, string | undefined>> = {
    relevance: RELEVANCE_HELP,
    citations: props.citationsNote,
    ...(props.gainsSpan && {
      rising: `By the citations gained between ${formatDay(props.gainsSpan.since)} and ${formatDay(props.gainsSpan.to)}`,
    }),
  };
  return (
    <div class="results__header">
      <p class="muted" aria-live="polite">
        {count === "loading" ? "Loading papers…" : count && countText(count)}
      </p>
      {model.sorts.length > 0 && (
        <fieldset class="segmented">
          <legend class="visually-hidden">Sort results</legend>
          {model.sorts.map((sort) => (
            <button
              key={sort}
              type="button"
              class={`segmented__option${model.sorted === sort ? " segmented__option--active" : ""}`}
              aria-pressed={model.sorted === sort}
              title={titles[sort]}
              onClick={() => props.onSort(sort)}
            >
              {SORT_LABELS[sort]}
            </button>
          ))}
          {model.relevanceHelp && (
            <button
              type="button"
              class="help"
              aria-expanded={props.relevanceHelpShown}
              aria-label="How is relevance computed?"
              title={RELEVANCE_HELP}
              onClick={props.onRelevanceHelp}
            >
              ?
            </button>
          )}
        </fieldset>
      )}
      {model.toggles && (
        <div class="results__toggles">
          <label class="toggle">
            <input type="checkbox" checked={props.hideSeen} onChange={props.onHideSeen} />
            Hide seen
          </label>
          <label class="toggle">
            <input type="checkbox" checked={props.showAbstracts} onChange={props.onShowAbstracts} />
            Show abstracts
          </label>
        </div>
      )}
      {model.exports && props.papers.length > 0 && (
        <details class="export-menu">
          <summary class="button export-menu__toggle">
            Export {props.papers.length.toLocaleString()}
          </summary>
          <div class="export-menu__items">
            {EXPORTS.map(({ label, file, type, render }) => (
              <button
                key={label}
                type="button"
                class="link-button"
                onClick={() => download(file, render(props.papers, props.citations), type)}
              >
                {label}
              </button>
            ))}
          </div>
        </details>
      )}
      {props.readingList && (
        <div class="results__actions">
          <button type="button" class="button" onClick={() => importInput.current?.click()}>
            Import
          </button>
          <input
            ref={importInput}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file) props.readingList?.onImport(file);
              event.currentTarget.value = "";
            }}
          />
        </div>
      )}
      {props.readingList && props.readingList.papers.length > 0 && (
        <div class="results__actions">
          <button
            type="button"
            class="button"
            onClick={() =>
              download(
                "reading-list.bib",
                toBibtexFile(props.readingList?.papers ?? []),
                "application/x-bibtex",
              )
            }
          >
            Export BibTeX
          </button>
          <button
            type="button"
            class="button"
            onClick={() =>
              download("reading-list.json", props.readingList?.json() ?? "", "application/json")
            }
          >
            Export JSON
          </button>
        </div>
      )}
    </div>
  );
}
