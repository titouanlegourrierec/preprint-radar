import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { toBibtex } from "../bibtex";
import { codeBadge, codeHost, codeUrl } from "../code";
import { download } from "../download";
import { PAPER_DRAG_TYPE } from "../folders";
import { countOf, daysSince, firstVersionYear, formatDay, subjectCode } from "../format";
import { highlight } from "../highlight";
import { useWholePaper } from "../hooks/use-whole-paper";
import { institutionsOf } from "../institutions";
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
import {
  AuthorsIcon,
  BrandIcon,
  CheckIcon,
  ChevronIcon,
  CiteIcon,
  EyeIcon,
  FolderIcon,
  GraphIcon,
  GripIcon,
  HeartIcon,
  HtmlIcon,
  InstitutionIcon,
  LinkIcon,
  PdfIcon,
  SelectChevron,
  StarIcon,
} from "./icons";
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

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
/** The sparks a saved paper's star bursts into (UX-37), each at its angle (styles.css). */
const SPARKS = 8;
/** How long the burst lasts, its longest animation and a little more. */
const BURST_MS = 800;

/**
 * A star flies from a card's button to the Reading list tab, then the tab bounces (UX-37):
 * only while the tab is in sight (the bar scrolls away with the list), drawn over the page
 * and gone once landed.
 */
function flyToReadingList(from: Element | null): void {
  const tab = document.querySelector<HTMLElement>('[data-tab="reading-list"]');
  const target = tab?.querySelector(".icon")?.getBoundingClientRect();
  const star = from?.querySelector("svg")?.cloneNode(true);
  if (!(tab && target && from && star instanceof SVGElement)) return;
  if (target.bottom < 0 || target.top > window.innerHeight) return;
  const start = from.getBoundingClientRect();
  const dx = target.left + target.width / 2 - (start.left + start.width / 2);
  const dy = target.top + target.height / 2 - (start.top + start.height / 2);
  star.classList.add("save-flight");
  star.style.left = `${start.left + start.width / 2 - 10}px`;
  star.style.top = `${start.top + start.height / 2 - 10}px`;
  document.body.append(star);
  // An arc: up past the tab's height at its middle, turning, then down onto it.
  const flight = star.animate(
    [
      { transform: "translate(0, 0) scale(1) rotate(0)" },
      {
        transform: `translate(${dx / 2}px, ${Math.min(dy / 2, 0) - 70}px) scale(1.5) rotate(200deg)`,
        offset: 0.45,
      },
      { transform: `translate(${dx}px, ${dy}px) scale(0.5) rotate(360deg)`, opacity: 0.3 },
    ],
    { duration: 750, easing: "cubic-bezier(0.45, 0, 0.25, 1)" },
  );
  flight.onfinish = () => {
    star.remove();
    // Restarted, should a second paper land before the first bounce ends.
    tab.classList.remove("tab--bump");
    void tab.offsetWidth;
    tab.classList.add("tab--bump");
  };
}

function matches(text: string, terms: readonly string[]): boolean {
  return highlight(text, terms).some((segment) => segment.match);
}

/** The first three ranks, in medal colors (UX-36). */
const MEDALS = ["gold", "silver", "bronze"] as const;

interface Props {
  paper: Paper;
  /** Its rank in the order shown, where the list ranks (Highly cited, UX-36). */
  rank?: number | undefined;
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
  /**
   * The reading list's folder of the paper, and the folders to put it in (UX-38): in the
   * reading list, once it has folders.
   */
  folder?:
    | { name: string | null; names: string[]; onChange: (name: string | null) => void }
    | undefined;
  /**
   * The reading list's cards are dragged by their handle (UX-39): onto a folder, or between
   * other cards in its own order, where `drop` says where one dragged over this would go.
   */
  drag?:
    | {
        dragging: boolean;
        drop: "before" | "after" | null;
        onStart: (arxivId: string) => void;
        onEnd: () => void;
      }
    | undefined;
}

export function PaperCard({
  paper,
  rank,
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
  folder,
  drag,
}: Props) {
  const [expanded, setExpanded] = useState(isTarget);
  // A paper of a search shard has no abstract nor comments: opening it, or asking for its
  // abstract, loads its day file (PERF-1).
  const [abstractWanted, setAbstractWanted] = useState(false);
  const whole = useWholePaper(paper, expanded || abstractWanted);
  const { abstract, comments } = whole.paper;
  const [bibtex, setBibtex] = useState<"" | "copied" | "downloaded">("");
  const [linkCopied, setLinkCopied] = useState(false);
  // Saved here, by its button or the s key: its star bursts, and flies to the tab (UX-37).
  const starButton = useRef<HTMLButtonElement>(null);
  const [burst, setBurst] = useState(0);
  const wasSaved = useRef(saved);
  useEffect(() => {
    if (saved && !wasSaved.current && !window.matchMedia(REDUCED_MOTION).matches) {
      setBurst((count) => count + 1);
      flyToReadingList(starButton.current);
    }
    wasSaved.current = saved;
  }, [saved]);
  useEffect(() => {
    if (burst === 0) return;
    const timer = setTimeout(() => setBurst(0), BURST_MS);
    return () => clearTimeout(timer);
  }, [burst]);
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
  const badge = code ? codeBadge(paper.code) : null;
  // An old paper announced lately, as a cross-list: the year it first went to arXiv (PROD-14).
  const firstVersion = firstVersionYear(paper.arxiv_id, paper.announced);
  // A recent paper has no citations yet: "0 citations" on nearly every card says nothing.
  const shownCitations =
    citations !== undefined && (citations > 0 || daysSince(paper.announced) >= YOUNG_DAYS)
      ? citations
      : undefined;
  const toggle = () => {
    if (expanded && isTarget) onClose();
    setExpanded(!expanded);
  };
  // A click on a folded card opens it, as its More button does (UX-34); its links and
  // controls keep their own, and so does a drag that selected text. An open card stays
  // open, its text free to click and select; Less (or o) folds it.
  const openOnClick = (event: MouseEvent) => {
    if (expanded || event.button !== 0 || event.defaultPrevented) return;
    const { target } = event;
    if (
      target instanceof Element &&
      target.closest("a, button, input, select, label, .paper__grip")
    )
      return;
    if (window.getSelection()?.toString()) return;
    setExpanded(true);
  };

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
    /* biome-ignore lint/a11y/useKeyWithClickEvents: the keyboard's way is the list's (o, or
       Enter on the focused card, `PaperList`), and More, which the click only shortens. */
    <article
      ref={root}
      class={`paper${expanded ? " paper--expanded" : ""}${isTarget ? " paper--target" : ""}${seen ? " paper--seen" : ""}${
        drag?.dragging ? " paper--dragging" : ""
      }${drag?.drop ? ` paper--drop-${drag.drop}` : ""}`}
      // Focused by the j and k keys of the list, which then act on this paper: named by
      // its title, which a screen reader then says.
      tabIndex={-1}
      aria-labelledby={titleId}
      data-arxiv-id={paper.arxiv_id}
      // The pointer's shortcut to More, which the keyboard has (o, Enter) and names.
      onClick={openOnClick}
      // Draggable only from its handle, so that its text is still selected by a drag.
      onDragStart={
        drag &&
        ((event) => {
          event.dataTransfer?.setData(PAPER_DRAG_TYPE, paper.arxiv_id);
          event.dataTransfer?.setData("text/plain", paper.abs_url);
          if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
          drag.onStart(paper.arxiv_id);
        })
      }
      onDragEnd={
        drag &&
        (() => {
          root.current?.removeAttribute("draggable");
          drag.onEnd();
        })
      }
    >
      {drag && (
        <span
          class="paper__grip"
          aria-hidden="true"
          title="Drag onto a folder, or between papers in My order (Alt+↑ ↓ from the keyboard)"
          onPointerDown={() => root.current?.setAttribute("draggable", "true")}
          onPointerUp={() => root.current?.removeAttribute("draggable")}
        >
          <GripIcon />
        </span>
      )}
      {rank !== undefined && (
        <span
          class={`paper__rank${rank <= MEDALS.length ? ` paper__rank--${MEDALS[rank - 1]}` : ""}`}
        >
          <span class="visually-hidden">Rank </span>
          {rank.toLocaleString()}
        </span>
      )}
      <div class="paper__main">
        <h2 class="paper__title" id={titleId}>
          <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
            <Highlighted text={paper.title} terms={highlights} />
          </a>
        </h2>

        <p class="paper__authors paper__line">
          <AuthorsIcon />
          <span>
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
          </span>
        </p>

        {affiliations.length > 0 && (
          <p class="paper__affiliations paper__line">
            <InstitutionIcon />
            <span>
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
            </span>
          </p>
        )}

        {abstract && (showAbstract || expanded) && (
          <p class={`paper__abstract${expanded ? "" : " paper__abstract--clamped"}`}>
            <RichText text={abstract} terms={highlights} />
          </p>
        )}
        {!abstract && paper.light !== undefined && (showAbstract || expanded) && (
          <p class="paper__abstract muted">
            {whole.loading ? (
              "Loading the abstract…"
            ) : whole.failed ? (
              "The abstract could not be loaded."
            ) : expanded || abstractWanted ? null : (
              <button type="button" class="link-button" onClick={() => setAbstractWanted(true)}>
                Load the abstract
              </button>
            )}
          </p>
        )}

        {expanded && (
          <p class="paper__report muted">
            Wrong author or affiliation? <a href={reportLink(paper)}>Report an error</a>.
          </p>
        )}

        {expanded && comments && (
          <p class="paper__comments">
            <RichText text={comments} terms={highlights} />
          </p>
        )}

        <footer class="paper__footer">
          <div class="paper__meta">
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
            {firstVersion !== null && (
              <span
                class="badge badge--muted"
                title={`First submitted to arXiv in ${firstVersion}, announced here on ${formatDay(paper.announced)}`}
              >
                first version {firstVersion}
              </span>
            )}
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
          </div>
          <div class="paper__actions">
            <a
              class="action"
              aria-describedby={titleId}
              href={paper.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <PdfIcon />
              PDF
            </a>
            {paper.html_url && (
              <a
                class="action"
                aria-describedby={titleId}
                href={paper.html_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <HtmlIcon />
                HTML
              </a>
            )}
            {paper.doi && (
              <a
                class="action"
                aria-describedby={titleId}
                href={`https://doi.org/${paper.doi}`}
                title="The published version"
                target="_blank"
                rel="noopener noreferrer"
              >
                <BrandIcon brand="doi" />
                DOI
              </a>
            )}
            {code && (
              // The stars of the code joined to its link, one badge (PROD-18).
              <span class="action-group">
                <a
                  class="action"
                  aria-describedby={titleId}
                  href={code}
                  title={code}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <BrandIcon brand={codeHost(code)} />
                  Code
                </a>
                {badge && (
                  <span
                    class={`action action--count stars${badge.shared ? " stars--shared" : ""}`}
                    title={badge.title}
                  >
                    {badge.icon === "star" ? <StarIcon filled /> : <HeartIcon />}
                    {badge.count}
                    <span class="visually-hidden"> {badge.noun}</span>
                    {badge.gained && <span class="stars__gained"> {badge.gained}</span>}
                    {badge.shared && <span class="stars__shared"> shared</span>}
                  </span>
                )}
              </span>
            )}
            <button type="button" aria-describedby={titleId} class="action" onClick={copyBibtex}>
              <CiteIcon />
              {bibtex === "copied" ? "Copied!" : bibtex === "downloaded" ? "Downloaded" : "BibTeX"}
            </button>
            <a
              class="action"
              aria-describedby={titleId}
              href={permalink}
              title="Copy a link to this paper"
              onClick={copyLink}
            >
              <LinkIcon />
              {linkCopied ? "Copied!" : "Share"}
            </a>
            {onShowInGraph && (
              <button
                type="button"
                aria-describedby={titleId}
                class="action"
                title="Show this paper in the graph, with its institutions"
                onClick={() => onShowInGraph(paper)}
              >
                <GraphIcon />
                Graph
              </button>
            )}
            {folder && (
              // A label, which a click on the card leaves alone (`openOnClick`).
              <label class="action action--select" title="Its folder in the reading list">
                <FolderIcon />
                <select
                  aria-label="Folder"
                  aria-describedby={titleId}
                  value={folder.name ?? ""}
                  onChange={(event) => folder.onChange(event.currentTarget.value || null)}
                >
                  <option value="">No folder</option>
                  {folder.names.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
                <SelectChevron />
              </label>
            )}
            {onToggleSeen && (
              <button
                type="button"
                aria-describedby={titleId}
                class="action"
                aria-pressed={seen}
                title="Seen papers are dimmed, and can be hidden (key x)"
                onClick={() => onToggleSeen(paper.arxiv_id)}
              >
                {/* One name, "Seen", its state said by aria-pressed; the mark is for the eye. */}
                <EyeIcon />
                Seen{seen && <CheckIcon />}
              </button>
            )}
            <button
              type="button"
              aria-describedby={titleId}
              class="action action--quiet paper__more"
              aria-expanded={expanded}
              onClick={toggle}
            >
              {expanded ? "Less" : "More"}
              <ChevronIcon up={expanded} />
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
          </div>
        </footer>
      </div>

      <button
        type="button"
        ref={starButton}
        class={`icon-button${saved ? " icon-button--active" : ""}${burst ? " icon-button--burst" : ""}`}
        aria-pressed={saved}
        aria-label="Save to reading list"
        aria-describedby={titleId}
        title={saved ? "Remove from reading list" : "Add to reading list"}
        // Whole once opened, so that the reading list keeps the abstract.
        onClick={() => onToggleSaved(whole.paper)}
      >
        {/* Keyed by the burst, so that a second save pops it again. */}
        <StarIcon key={`star-${burst}`} filled={saved} />
        {burst > 0 && (
          <span key={`burst-${burst}`} class="save-burst" aria-hidden="true">
            {Array.from({ length: SPARKS }, (_, index) => (
              <i key={index} />
            ))}
          </span>
        )}
      </button>
    </article>
  );
}
