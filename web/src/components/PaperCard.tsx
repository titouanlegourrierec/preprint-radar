import { useEffect, useRef, useState } from "preact/hooks";
import { toBibtex } from "../bibtex";
import { formatDay, subjectCode } from "../format";
import { highlight } from "../highlight";
import type { Paper } from "../types";
import { Highlighted } from "./Highlighted";
import { RichText } from "./RichText";

const MAX_AUTHORS_COLLAPSED = 6;
const MAX_AFFILIATIONS_COLLAPSED = 3;

function matches(text: string, terms: readonly string[]): boolean {
  return highlight(text, terms).some((segment) => segment.match);
}

interface Props {
  paper: Paper;
  highlights: readonly string[];
  showAbstract: boolean;
  saved: boolean;
  /** Whether a shared `?paper=` link points at this paper. */
  isTarget: boolean;
  /** Query string linking to this paper alone, for the Share control. */
  permalink: string;
  onOpen: (arxivId: string) => void;
  /** Absent for papers the graph cannot show (the archive). */
  onShowInGraph?: ((paper: Paper) => void) | undefined;
  /** Citation count, when known. */
  citations?: number | undefined;
  /** Where and when the count comes from, for its tooltip. */
  citationsNote?: string | undefined;
  onToggleSaved: (paper: Paper) => void;
  onAuthor: (author: string) => void;
  onAffiliation: (affiliation: string) => void;
}

export function PaperCard({
  paper,
  highlights,
  showAbstract,
  saved,
  isTarget,
  permalink,
  onOpen,
  onShowInGraph,
  citations,
  citationsNote,
  onToggleSaved,
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

  // Plain click: copy the link and anchor the URL, without reloading. Modified
  // clicks keep their meaning (open in a new tab...), the href being a real link.
  async function copyLink(event: MouseEvent) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    onOpen(paper.arxiv_id);
    setExpanded(true);
    try {
      await navigator.clipboard.writeText(new URL(permalink, window.location.href).toString());
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 1500);
    } catch {
      // Clipboard access can be denied; the address bar still holds the link.
    }
  }

  return (
    <article
      ref={root}
      class={`paper${expanded ? " paper--expanded" : ""}${isTarget ? " paper--target" : ""}`}
    >
      <div class="paper__main">
        <h2 class="paper__title">
          <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
            <Highlighted text={paper.title} terms={highlights} />
          </a>
        </h2>

        <p class="paper__authors">
          {authors.map((author, index) => (
            <span key={author}>
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
                  onClick={() => onAffiliation(affiliation)}
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

        {expanded && paper.comments && (
          <p class="paper__comments">
            <RichText text={paper.comments} terms={highlights} />
          </p>
        )}

        <footer class="paper__meta">
          {paper.venue && (
            <span
              class={`badge${paper.venue.endsWith("Workshop") ? " badge--muted" : ""}`}
              title={paper.comments ?? paper.journal_ref ?? undefined}
            >
              <Highlighted text={paper.venue} terms={highlights} />
            </span>
          )}
          <span>{formatDay(paper.announced)}</span>
          {citations !== undefined && citations > 0 && (
            <span class="citations" title={citationsNote}>
              {citations.toLocaleString()} citation{citations === 1 ? "" : "s"}
            </span>
          )}
          {subject && <span title={paper.primary_subject ?? undefined}>{subject}</span>}
          <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer">
            PDF
          </a>
          {paper.html_url && (
            <a href={paper.html_url} target="_blank" rel="noopener noreferrer">
              HTML
            </a>
          )}
          <button type="button" class="link-button" onClick={copyBibtex}>
            {copied ? "Copied!" : "BibTeX"}
          </button>
          <a href={permalink} title="Copy a link to this paper" onClick={copyLink}>
            {linkCopied ? "Copied!" : "Share"}
          </a>
          {onShowInGraph && (
            <button
              type="button"
              class="link-button"
              title="Show this paper in the graph, with its institutions"
              onClick={() => onShowInGraph(paper)}
            >
              Graph
            </button>
          )}
          {hasDetails && (
            <button
              type="button"
              class="link-button"
              aria-expanded={expanded}
              onClick={() => setExpanded(!expanded)}
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
        title={saved ? "Remove from reading list" : "Add to reading list"}
        onClick={() => onToggleSaved(paper)}
      >
        {saved ? "★" : "☆"}
      </button>
    </article>
  );
}
