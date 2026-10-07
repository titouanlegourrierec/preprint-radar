import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { toBibtex } from "../bibtex";
import { codeUrl } from "../code";
import { download } from "../download";
import { countOf, daysSince, formatDay, subjectCode } from "../format";
import { highlight } from "../highlight";
import { institutionsOf } from "../institutions";
import { linkOuts } from "../link-outs";
import { reportLink } from "../report";
import {
  affiliationNeedles,
  exactly,
  type NameFilter,
  type NameHighlights,
  typed,
} from "../search";
import type { Paper } from "../types";
import { Highlighted } from "./Highlighted";
import { RichText } from "./RichText";

const MAX_AUTHORS_COLLAPSED = 6;
const MAX_AFFILIATIONS_COLLAPSED = 3;
/** Days under which a paper's count of 0 is not shown: counts need weeks to start. */
const YOUNG_DAYS = 60;

/**
 * What a click on one of the paper's affiliations filters on: its institution, exactly, as
 * the graph and Rankings name it, so that "Show papers" agrees with them; the string itself
 * (matching word prefixes) when it names no institution, like a department alone.
 */
export function affiliationFilter(paper: Paper, affiliation: string): NameFilter {
  const institution = institutionsOf(paper)[paper.affiliations?.indexOf(affiliation) ?? -1];
  return institution ? exactly(institution) : typed(affiliation);
}

function matches(text: string, terms: readonly string[]): boolean {
  return highlight(text, terms).some((segment) => segment.match);
}

interface Props {
  paper: Paper;
  highlights: readonly string[];
  /** The names filtered on, highlighted in the author and affiliation lines only (SRCH-8). */
  nameHighlights: NameHighlights;
  showAbstract: boolean;
  saved: boolean;
  /** Marked seen by the reader: dimmed in the list. */
  seen: boolean;
  /** Whether a shared `?paper=` link points at this paper. */
  isTarget: boolean;
  /** Query string linking to this paper alone, for the Share control. */
  permalink: string;
  onOpen: (arxivId: string) => void;
  /** The target of a shared link was folded: it is no longer the paper shown. */
  onClose: () => void;
  /** Absent for papers the graph cannot show (the archive). */
  onShowInGraph?: ((paper: Paper) => void) | undefined;
  /** Citation count, when known. */
  citations?: number | undefined;
  /** Where and when the count comes from, for its tooltip. */
  citationsNote?: string | undefined;
  /** The citations it gained in the last week of counts, when it gained any. */
  gain?: { text: string; title: string } | undefined;
  onToggleSaved: (paper: Paper) => void;
  /** Absent where papers cannot be marked seen (the reading list). */
  onToggleSeen?: ((arxivId: string) => void) | undefined;
  onAuthor: (author: string) => void;
  /** The affiliation's institution, exactly, or the string itself when it names none. */
  onAffiliation: (filter: NameFilter) => void;
}

export function PaperCard({
  paper,
  highlights,
  nameHighlights,
  showAbstract,
  saved,
  seen,
  isTarget,
  permalink,
  onOpen,
  onClose,
  onShowInGraph,
  citations,
  citationsNote,
  gain,
  onToggleSaved,
  onToggleSeen,
  onAuthor,
  onAffiliation,
}: Props) {
  const [expanded, setExpanded] = useState(isTarget);
  const [bibtex, setBibtex] = useState<"" | "copied" | "downloaded">("");
  const [linkCopied, setLinkCopied] = useState(false);
  const root = useRef<HTMLElement>(null);
  // A "+N" opens the card and goes away: the first name it showed takes the focus, which
  // would otherwise fall to the page (and "j" back to the first card).
  const [revealing, setRevealing] = useState<"authors" | "affiliations" | null>(null);
  const revealed = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    if (revealing === null) return;
    revealed.current?.focus();
    setRevealing(null);
  }, [revealing]);
  const reveal = (list: "authors" | "affiliations") => {
    setExpanded(true);
    setRevealing(list);
  };

  // A shared link's target is scrolled into view once, when the list first shows it.
  const targetOnMount = useRef(isTarget);
  useEffect(() => {
    if (targetOnMount.current) root.current?.scrollIntoView({ block: "center" });
  }, []);

  const authors =
    expanded || paper.authors.length <= MAX_AUTHORS_COLLAPSED
      ? paper.authors
      : paper.authors.slice(0, MAX_AUTHORS_COLLAPSED);
  // Names are marked with the search words and the names filtered on, each in its line;
  // an affiliation of the institution clicked is marked whole, however it writes it.
  const authorTerms = [...highlights, ...nameHighlights.authors];
  const affiliationTerms = (affiliation: string) =>
    affiliationNeedles(paper, affiliation, nameHighlights, highlights);
  // Matching affiliations first, so that a filtered one is never hidden behind "+N".
  const allAffiliations = [...(paper.affiliations ?? [])].sort(
    (a, b) => Number(matches(b, affiliationTerms(b))) - Number(matches(a, affiliationTerms(a))),
  );
  const affiliations = expanded
    ? allAffiliations
    : allAffiliations.slice(0, MAX_AFFILIATIONS_COLLAPSED);
  const code = codeUrl(paper);
  // A recent paper has no citations yet: "0 citations" on nearly every card says nothing.
  const shownCitations =
    citations !== undefined && (citations > 0 || daysSince(paper.announced) >= YOUNG_DAYS)
      ? citations
      : undefined;
  // The controls of every card read alike ("PDF", "Share"): each names its paper.
  const titleId = `title-${paper.arxiv_id}`;
  const subject = [paper.primary_subject && subjectCode(paper.primary_subject)]
    .concat(paper.cross_list_from ? ["cross-list"] : [])
    .filter(Boolean)
    .join(" · ");

  async function copyBibtex() {
    try {
      await navigator.clipboard.writeText(toBibtex(paper));
      setBibtex("copied");
    } catch {
      // A refused clipboard: the entry as a file instead, and the button says so.
      download(`${paper.arxiv_id.replace("/", "_")}.bib`, toBibtex(paper), "application/x-bibtex");
      setBibtex("downloaded");
    }
    setTimeout(() => setBibtex(""), 1500);
  }

  // Plain click: copy the link, and say so; nothing else changes. Only when the clipboard
  // is refused does the address bar show the link, to copy from there. Modified clicks keep
  // their meaning (open in a new tab...), the href being a real link.
  async function copyLink(event: MouseEvent) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    try {
      await navigator.clipboard.writeText(new URL(permalink, window.location.href).toString());
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 1500);
    } catch {
      // Open, so that its Less button folds it back and clears the address bar.
      onOpen(paper.arxiv_id);
      setExpanded(true);
    }
  }

  return (
    <article
      ref={root}
      class={`paper${expanded ? " paper--expanded" : ""}${isTarget ? " paper--target" : ""}${seen ? " paper--seen" : ""}`}
      // Focused by the j and k keys of the list, which then act on this paper: named by
      // its title, which a screen reader then says.
      tabIndex={-1}
      aria-labelledby={titleId}
      data-arxiv-id={paper.arxiv_id}
    >
      <div class="paper__main">
        <h2 class="paper__title" id={titleId}>
          <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
            <Highlighted text={paper.title} terms={highlights} />
          </a>
        </h2>

        <p class="paper__authors">
          {authors.map((author, index) => (
            // Two authors may share a name.
            <span key={`${index}:${author}`}>
              {index > 0 && ", "}
              <button
                ref={revealing === "authors" && index === MAX_AUTHORS_COLLAPSED ? revealed : null}
                type="button"
                class="link-button"
                title="Show papers by this author"
                onClick={() => onAuthor(author)}
              >
                <Highlighted text={author} terms={authorTerms} />
              </button>
            </span>
          ))}
          {authors.length < paper.authors.length && (
            <>
              {" "}
              <button
                type="button"
                class="link-button muted"
                aria-describedby={titleId}
                title={`Show all ${paper.authors.length} authors`}
                onClick={() => reveal("authors")}
              >
                +{paper.authors.length - authors.length}
                <span class="visually-hidden"> more authors</span>
              </button>
            </>
          )}
        </p>

        {affiliations.length > 0 && (
          <p class="paper__affiliations">
            {affiliations.map((affiliation, index) => (
              <span key={affiliation}>
                {index > 0 && "\u00a0· "}
                <button
                  ref={
                    revealing === "affiliations" && index === MAX_AFFILIATIONS_COLLAPSED
                      ? revealed
                      : null
                  }
                  type="button"
                  class="link-button"
                  title="Show papers from this affiliation"
                  onClick={() => onAffiliation(affiliationFilter(paper, affiliation))}
                >
                  <Highlighted text={affiliation} terms={affiliationTerms(affiliation)} />
                </button>
              </span>
            ))}
            {affiliations.length < allAffiliations.length && (
              <>
                {" "}
                <button
                  type="button"
                  class="link-button"
                  aria-describedby={titleId}
                  title={`Show all ${allAffiliations.length} affiliations`}
                  onClick={() => reveal("affiliations")}
                >
                  +{allAffiliations.length - affiliations.length}
                  <span class="visually-hidden"> more affiliations</span>
                </button>
              </>
            )}
          </p>
        )}

        {paper.abstract && (showAbstract || expanded) && (
          <p class={`paper__abstract${expanded ? "" : " paper__abstract--clamped"}`}>
            <RichText text={paper.abstract} terms={highlights} />
          </p>
        )}

        {expanded && (
          <p class="paper__elsewhere">
            Related work:{" "}
            {linkOuts(paper.arxiv_id).map((link, index) => (
              <span key={link.name}>
                {index > 0 && "\u00a0· "}
                <a href={link.url} title={link.title} target="_blank" rel="noopener noreferrer">
                  {link.name}
                </a>
              </span>
            ))}
          </p>
        )}

        {expanded && (
          <p class="paper__report muted">
            Wrong author or affiliation? <a href={reportLink(paper)}>Report an error</a>.
          </p>
        )}

        {expanded && paper.comments && (
          <p class="paper__comments">
            <RichText text={paper.comments} terms={highlights} />
          </p>
        )}

        <footer class="paper__meta">
          {paper.withdrawn && (
            <span
              class="badge badge--withdrawn"
              title="Its authors withdrew it from arXiv; its comments say why"
            >
              Withdrawn
            </span>
          )}
          {paper.venue && (
            <span
              class={`badge${paper.venue.endsWith("Workshop") ? " badge--muted" : ""}`}
              title={paper.comments ?? paper.journal_ref ?? undefined}
            >
              <Highlighted text={paper.venue} terms={highlights} />
            </span>
          )}
          <span>{formatDay(paper.announced)}</span>
          {shownCitations !== undefined && (
            <span
              class={`citations${shownCitations > 0 ? " citations--some" : ""}`}
              title={citationsNote}
            >
              {countOf(shownCitations, "citation")}
            </span>
          )}
          {gain && (
            <span class="citations citations--gain" title={gain.title}>
              {gain.text}
            </span>
          )}
          {subject && <span title={paper.primary_subject ?? undefined}>{subject}</span>}
          <a
            aria-describedby={titleId}
            href={paper.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            PDF
          </a>
          {paper.html_url && (
            <a
              aria-describedby={titleId}
              href={paper.html_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              HTML
            </a>
          )}
          {paper.doi && (
            <a
              aria-describedby={titleId}
              href={`https://doi.org/${paper.doi}`}
              title="The published version"
              target="_blank"
              rel="noopener noreferrer"
            >
              DOI
            </a>
          )}
          {code && (
            <a
              aria-describedby={titleId}
              href={code}
              title={code}
              target="_blank"
              rel="noopener noreferrer"
            >
              Code
            </a>
          )}
          <button type="button" aria-describedby={titleId} class="link-button" onClick={copyBibtex}>
            {bibtex === "copied" ? "Copied!" : bibtex === "downloaded" ? "Downloaded" : "BibTeX"}
          </button>
          <a
            aria-describedby={titleId}
            href={permalink}
            title="Copy a link to this paper"
            onClick={copyLink}
          >
            {linkCopied ? "Copied!" : "Share"}
          </a>
          {onShowInGraph && (
            <button
              type="button"
              aria-describedby={titleId}
              class="link-button"
              title="Show this paper in the graph, with its institutions"
              onClick={() => onShowInGraph(paper)}
            >
              Graph
            </button>
          )}
          {onToggleSeen && (
            <button
              type="button"
              aria-describedby={titleId}
              class="link-button"
              aria-pressed={seen}
              title="Seen papers are dimmed, and can be hidden (key x)"
              onClick={() => onToggleSeen(paper.arxiv_id)}
            >
              {/* One name, "Seen", its state said by aria-pressed; the mark is for the eye. */}
              Seen{seen && <span aria-hidden="true"> ✓</span>}
            </button>
          )}
          <button
            type="button"
            aria-describedby={titleId}
            class="link-button paper__more"
            aria-expanded={expanded}
            onClick={() => {
              if (expanded && isTarget) onClose();
              setExpanded(!expanded);
            }}
          >
            {expanded ? "Less" : "More"}
          </button>
          {/* What a copy did, said to screen readers: the buttons' text changes silently. */}
          <span class="visually-hidden" role="status">
            {bibtex === "copied"
              ? "BibTeX copied"
              : bibtex === "downloaded"
                ? "BibTeX downloaded: the clipboard was refused"
                : linkCopied
                  ? "Link copied"
                  : ""}
          </span>
        </footer>
      </div>

      <button
        type="button"
        class={`icon-button${saved ? " icon-button--active" : ""}`}
        aria-pressed={saved}
        aria-label="Save to reading list"
        aria-describedby={titleId}
        title={saved ? "Remove from reading list" : "Add to reading list"}
        onClick={() => onToggleSaved(paper)}
      >
        <span aria-hidden="true">{saved ? "★" : "☆"}</span>
      </button>
    </article>
  );
}
