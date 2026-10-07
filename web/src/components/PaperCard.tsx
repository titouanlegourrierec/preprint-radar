import { useEffect, useRef, useState } from "preact/hooks";
import { toBibtex } from "../bibtex";
import { codeUrl } from "../code";
import { daysSince, formatDay, subjectCode } from "../format";
import { highlight } from "../highlight";
import { institutionsOf } from "../institutions";
import { linkOuts } from "../link-outs";
import { reportLink } from "../report";
import { exactly, type NameFilter, typed } from "../search";
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
  onToggleSaved,
  onToggleSeen,
  onAuthor,
  onAffiliation,
}: Props) {
  const [expanded, setExpanded] = useState(isTarget);
  const [copied, setCopied] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const root = useRef<HTMLElement>(null);

  // A shared link's target is scrolled into view once, when the list first shows it.
  const targetOnMount = useRef(isTarget);
  useEffect(() => {
    if (targetOnMount.current) root.current?.scrollIntoView({ block: "center" });
  }, []);

  const authors =
    expanded || paper.authors.length <= MAX_AUTHORS_COLLAPSED
      ? paper.authors
      : paper.authors.slice(0, MAX_AUTHORS_COLLAPSED);
  // Matching affiliations first, so that a filtered one is never hidden behind "+N".
  const allAffiliations = [...(paper.affiliations ?? [])].sort(
    (a, b) => Number(matches(b, highlights)) - Number(matches(a, highlights)),
  );
  const affiliations = expanded
    ? allAffiliations
    : allAffiliations.slice(0, MAX_AFFILIATIONS_COLLAPSED);
  const hasDetails = Boolean(paper.abstract || paper.comments);
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
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied; nothing sensible to do.
    }
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
      // Focused by the j and k keys of the list, which then act on this paper.
      tabIndex={-1}
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
                type="button"
                class="link-button"
                title="Show papers by this author"
                onClick={() => onAuthor(author)}
              >
                <Highlighted text={author} terms={highlights} />
              </button>
            </span>
          ))}
          {authors.length < paper.authors.length && (
            <span class="muted"> +{paper.authors.length - authors.length}</span>
          )}
        </p>

        {affiliations.length > 0 && (
          <p class="paper__affiliations">
            {affiliations.map((affiliation, index) => (
              <span key={affiliation}>
                {index > 0 && "\u00a0· "}
                <button
                  type="button"
                  class="link-button"
                  title="Show papers from this affiliation"
                  onClick={() => onAffiliation(affiliationFilter(paper, affiliation))}
                >
                  <Highlighted text={affiliation} terms={highlights} />
                </button>
              </span>
            ))}
            {affiliations.length < allAffiliations.length && (
              <span> +{allAffiliations.length - affiliations.length}</span>
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
              {shownCitations.toLocaleString()} citation{shownCitations === 1 ? "" : "s"}
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
            {copied ? "Copied!" : "BibTeX"}
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
              {seen ? "Seen ✓" : "Mark seen"}
            </button>
          )}
          {hasDetails && (
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
          )}
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
