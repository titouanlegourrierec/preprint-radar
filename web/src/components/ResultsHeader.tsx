import type { ComponentChildren } from "preact";
import { useRef } from "preact/hooks";
import { toBibtexFile } from "../bibtex";
import { download } from "../download";
import { toCsv, toMarkdown, toRis } from "../export";
import { countOf, formatDay } from "../format";
import { LOCALE } from "../locale";
import type { Paper } from "../types";
import type { CountLine, SortChoice, ViewModel } from "../view-model";
import { InfoButton } from "./InfoButton";
import { DownloadIcon, UploadIcon } from "./icons";
import { Segmented } from "./Segmented";

// The exports of the results shown, as files named after the list ("papers.bib",
// "reading-list.bib").
const EXPORTS: {
  label: string;
  extension: string;
  type: string;
  render: (papers: Paper[], citations: ReadonlyMap<string, number>) => string;
}[] = [
  {
    label: "BibTeX",
    extension: "bib",
    type: "application/x-bibtex",
    render: (papers) => toBibtexFile(papers),
  },
  { label: "CSV", extension: "csv", type: "text/csv", render: toCsv },
  {
    label: "RIS",
    extension: "ris",
    type: "application/x-research-info-systems",
    render: (papers) => toRis(papers),
  },
  {
    label: "Markdown",
    extension: "md",
    type: "text/markdown",
    render: (papers) => toMarkdown(papers),
  },
];

export const RELEVANCE_HELP =
  "Relevance ranks papers by how well they match your search words. Rarer words weigh more, " +
  "and a match counts most in the title, then in authors, affiliations, the abstract and " +
  "comments. Exact words count more than partial or approximate ones, and your words side " +
  "by side, as you typed them, more than apart.";

const SORT_LABELS: Record<SortChoice, string> = {
  relevance: "Relevance",
  newest: "Newest",
  citations: "Most cited",
  rising: "Rising",
  stars: "Most starred",
  custom: "My order",
};

const STARS_TITLE =
  "By the GitHub stars of the code they link. A repository other papers link too, or a " +
  "folder of a larger one, ranks with the papers without stars: its stars are not the " +
  "paper's alone.";

interface Props {
  model: ViewModel;
  /**
   * What the header counts, or what is loading ("Loading 3,646 papers of 5 days…");
   * `null` while there is nothing to count.
   */
  count: CountLine | { loading: string } | null;
  onSort: (sort: SortChoice) => void;
  /** Where the counts come from, for Most cited's tooltip. */
  citationsNote: string | undefined;
  /** The days Rising's gains span, for its tooltip. */
  gainsSpan: { since: string; to: string } | null;
  /** What the view says of its papers: an ⓘ beside the count (UX-33). */
  notes?: ComponentChildren;
  /** The button folding the sidebar, before the count (UX-35). */
  sidebarToggle?: ComponentChildren;
  /** The view's own controls, after the count: Rankings' (UX-33). */
  controls?: ComponentChildren;
  hideSeen: boolean;
  onHideSeen: () => void;
  showAbstracts: boolean;
  onShowAbstracts: () => void;
  /** The papers shown, for the Export menu, with their citation counts. */
  papers: Paper[];
  citations: ReadonlyMap<string, number>;
  /** The reading list's own tools, in its view, beside the Export menu. */
  readingList?:
    | {
        /** Every saved paper, whatever the search shows of them. */
        papers: Paper[];
        onImport: (file: File) => void;
        /** The list as a JSON file, its saved searches with it. */
        json: () => string;
      }
    | undefined;
}

function countText(count: CountLine): string {
  return `${count.shown.toLocaleString(LOCALE)} of ${countOf(count.total, count.noun)}${count.tail ?? ""}`;
}

/**
 * The top of a list: how many papers it shows, its order, its toggles, and what it can
 * export or import.
 */
export function ResultsHeader(props: Props) {
  const { model, count } = props;
  const importInput = useRef<HTMLInputElement>(null);
  const exportName = props.readingList ? "reading-list" : "papers";
  const titles: Partial<Record<SortChoice, string | undefined>> = {
    relevance: RELEVANCE_HELP,
    citations: props.citationsNote,
    stars: STARS_TITLE,
    ...(props.gainsSpan && {
      rising: `By the citations gained between ${formatDay(props.gainsSpan.since)} and ${formatDay(props.gainsSpan.to)}`,
    }),
  };
  return (
    <div class="results__header">
      <div class="results__count">
        {props.sidebarToggle}
        <p class="muted" aria-live="polite">
          {count && ("loading" in count ? count.loading : countText(count))}
        </p>
        {props.notes}
      </div>
      {props.controls}
      {model.sorts.length > 0 && (
        <Segmented
          legend="Sort results"
          options={model.sorts.map((sort) => [sort, SORT_LABELS[sort]] as const)}
          value={model.sorted}
          onChange={props.onSort}
          titles={titles}
        >
          {model.relevanceHelp && (
            <InfoButton label="How is relevance computed?" end>
              <p>{RELEVANCE_HELP}</p>
            </InfoButton>
          )}
        </Segmented>
      )}
      {(model.hideSeen || model.abstracts) && (
        <div class="results__toggles">
          {model.hideSeen && (
            <label class="toggle">
              <input type="checkbox" checked={props.hideSeen} onChange={props.onHideSeen} />
              Hide seen
            </label>
          )}
          {model.abstracts && (
            <label class="toggle">
              <input
                type="checkbox"
                checked={props.showAbstracts}
                onChange={props.onShowAbstracts}
              />
              Show abstracts
            </label>
          )}
        </div>
      )}
      {model.exports && props.papers.length > 0 && (
        <details class="export-menu">
          <summary class="button export-menu__toggle">
            <DownloadIcon />
            Export {props.papers.length.toLocaleString(LOCALE)}
          </summary>
          <div class="export-menu__items">
            {EXPORTS.map(({ label, extension, type, render }) => (
              <button
                key={label}
                type="button"
                class="link-button"
                onClick={() =>
                  download(
                    `${exportName}.${extension}`,
                    render(props.papers, props.citations),
                    type,
                  )
                }
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
            <UploadIcon />
            Import library
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
          {props.readingList.papers.length > 0 && (
            <button
              type="button"
              class="button"
              title="The whole list, its folders and saved searches, to import in another browser"
              onClick={() =>
                download("reading-list.json", props.readingList?.json() ?? "", "application/json")
              }
            >
              <DownloadIcon />
              Export library
            </button>
          )}
        </div>
      )}
    </div>
  );
}
