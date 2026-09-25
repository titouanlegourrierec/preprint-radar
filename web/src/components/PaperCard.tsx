import { useState } from "preact/hooks";
import { toBibtex } from "../bibtex";
import type { Paper } from "../types";
import { Highlighted } from "./Highlighted";

const MAX_AUTHORS_COLLAPSED = 8;

interface Props {
  paper: Paper;
  highlights: readonly string[];
  saved: boolean;
  onToggleSaved: (paper: Paper) => void;
  onAuthor: (author: string) => void;
  onAffiliation: (affiliation: string) => void;
}

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function subjectCode(subject: string): string {
  return /\(([^()]+)\)\s*$/.exec(subject)?.[1] ?? subject;
}

export function PaperCard({
  paper,
  highlights,
  saved,
  onToggleSaved,
  onAuthor,
  onAffiliation,
}: Props) {
  const [showAllAuthors, setShowAllAuthors] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const authors =
    showAllAuthors || paper.authors.length <= MAX_AUTHORS_COLLAPSED
      ? paper.authors
      : paper.authors.slice(0, MAX_AUTHORS_COLLAPSED);

  async function copyBibtex() {
    try {
      await navigator.clipboard.writeText(toBibtex(paper));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied; nothing sensible to do.
    }
  }

  return (
    <article class="paper">
      <header class="paper__header">
        <h2 class="paper__title">
          <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
            <Highlighted text={paper.title} terms={highlights} />
          </a>
        </h2>
        <button
          type="button"
          class={`icon-button${saved ? " icon-button--active" : ""}`}
          aria-pressed={saved}
          title={saved ? "Remove from reading list" : "Add to reading list"}
          onClick={() => onToggleSaved(paper)}
        >
          {saved ? "★" : "☆"}
        </button>
      </header>

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
          <button type="button" class="link-button muted" onClick={() => setShowAllAuthors(true)}>
            {" "}
            +{paper.authors.length - authors.length} more
          </button>
        )}
      </p>

      {paper.affiliations && paper.affiliations.length > 0 && (
        <ul class="chips" aria-label="Affiliations">
          {paper.affiliations.map((affiliation) => (
            <li key={affiliation}>
              <button
                type="button"
                class="chip"
                title="Show papers from this affiliation"
                onClick={() => onAffiliation(affiliation)}
              >
                <Highlighted text={affiliation} terms={highlights} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {paper.abstract && (
        <p class={`paper__abstract${expanded ? "" : " paper__abstract--clamped"}`}>
          <Highlighted text={paper.abstract} terms={highlights} />
        </p>
      )}
      {paper.abstract && (
        <button type="button" class="link-button muted" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show less" : "Show more"}
        </button>
      )}

      {paper.comments && (
        <p class="paper__comments">
          <Highlighted text={paper.comments} terms={highlights} />
        </p>
      )}

      <footer class="paper__footer">
        <span class="muted">{formatDate(paper.announced)}</span>
        <span class="badge" title={paper.primary_subject ?? undefined}>
          {subjectCode(paper.primary_subject ?? "")}
        </span>
        {paper.cross_list_from && <span class="badge badge--muted">cross-list</span>}
        <span class="paper__links">
          <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer">
            PDF
          </a>
          {paper.html_url && (
            <a href={paper.html_url} target="_blank" rel="noopener noreferrer">
              HTML
            </a>
          )}
          <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
            arXiv:{paper.arxiv_id}
          </a>
          <button type="button" class="link-button" onClick={copyBibtex}>
            {copied ? "Copied!" : "BibTeX"}
          </button>
        </span>
      </footer>
    </article>
  );
}
