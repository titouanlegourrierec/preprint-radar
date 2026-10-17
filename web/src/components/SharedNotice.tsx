import { countOf } from "../format";
import { LOCALE } from "../locale";
import type { Paper } from "../types";
import { StarIcon } from "./icons";

/** Ids named one by one before "and N more". */
const LISTED = 10;

interface Props {
  name: string;
  /** How many papers the link names. */
  asked: number;
  found:
    | { status: "loading" }
    | { status: "ready"; papers: Paper[]; missing: string[] }
    | { status: "error" };
  /** The name of this browser's folder of the same name, which the papers would join. */
  existing: string | null;
  onAdd: () => void;
  onRetry: () => void;
  onClose: () => void;
}

/**
 * Above the papers of a folder a link shares (UX-46): what it is, the papers the site's
 * data does not hold (as arXiv links), and the way to add them to one's reading list, in a
 * folder of that name, or to close it.
 */
export function SharedNotice({ name, asked, found, existing, onAdd, onRetry, onClose }: Props) {
  if (found.status === "loading") {
    return (
      <p class="notice shared-notice" role="status">
        Finding the {countOf(asked, "paper")} of “{name}”, a folder shared with you…
      </p>
    );
  }
  const close = (
    <button type="button" class="link-button" onClick={onClose}>
      Close
    </button>
  );
  if (found.status === "error") {
    return (
      <p class="notice notice--error shared-notice" role="alert">
        The papers of “{name}”, a folder shared with you, could not be loaded.{" "}
        <button type="button" class="link-button" onClick={onRetry}>
          Retry
        </button>{" "}
        · {close}
      </p>
    );
  }
  const { papers, missing } = found;
  const outside =
    papers.length === 0
      ? `none of its ${countOf(missing.length, "paper")} is`
      : `${countOf(papers.length, "paper")}; ${countOf(missing.length, "other")} ${missing.length === 1 ? "is" : "are"} not`;
  return (
    <div class="notice shared-notice" role="status">
      <p>
        <strong>“{name}”</strong>, a folder shared with you:{" "}
        {missing.length === 0 ? (
          countOf(papers.length, "paper")
        ) : (
          <>
            {outside} in Preprint Radar's data, on arXiv:{" "}
            {missing.slice(0, LISTED).map((id, index) => (
              <span key={id}>
                {index > 0 && ", "}
                <a href={`https://arxiv.org/abs/${id}`} target="_blank" rel="noopener noreferrer">
                  {id}
                </a>
              </span>
            ))}
            {missing.length > LISTED &&
              ` and ${(missing.length - LISTED).toLocaleString(LOCALE)} more`}
          </>
        )}
        .
      </p>
      <p class="shared-notice__actions">
        {papers.length > 0 && (
          <button type="button" class="button" onClick={onAdd}>
            <StarIcon />
            {existing ? `Add them to my “${existing}”` : "Add to my reading list"}
          </button>
        )}
        {close}
      </p>
    </div>
  );
}
