import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { LOCALE } from "../locale";
import { shareLink } from "../native-share";
import { type SavedSearch, type SearchOf, savedSearch, searchOf } from "../saved-searches";
import type { PaperIndex } from "../search";
import { CheckIcon, LinkIcon } from "./icons";

interface Props {
  searches: SavedSearch[];
  /** The loaded papers, which each search runs over. */
  index: PaperIndex | null;
  /** Newest day of the previous visit: papers after it count as new. */
  since: string | null;
  /** The search shown now, which can be saved. */
  current: SearchOf;
  onSave: () => void;
  onRemove: (saved: SavedSearch) => void;
  /** Show a saved search's papers; `onlyNew` when its count is of new papers. */
  onOpen: (saved: SavedSearch, onlyNew: boolean) => void;
}

/** The saved searches and how many papers each finds: new since the last visit, or loaded. */
export function SavedSearches({
  searches,
  index,
  since,
  current,
  onSave,
  onRemove,
  onOpen,
}: Props) {
  const counts = useMemo(
    () =>
      searches.map((saved) => {
        if (index === null) return null;
        const { query, filters } = searchOf(saved);
        const found = index.search(query, filters, "newest");
        return since === null
          ? found.length
          : found.filter(({ paper }) => paper.announced > since).length;
      }),
    [searches, index, since],
  );
  const shown = savedSearch(current);
  const savedShown = shown && searches.find(({ search }) => search === shown.search);
  // The search saved last, which arrives with a bump (UX-59); none of those already there
  // when the list first draws.
  const known = useRef<ReadonlySet<string> | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  useEffect(() => {
    const fresh = known.current && searches.find(({ search }) => !known.current?.has(search));
    if (fresh) setAdded(fresh.search);
    known.current = new Set(searches.map(({ search }) => search));
  }, [searches]);
  // The link of the search shown, as the address bar holds it (its period, view and sort
  // too): a phone's share sheet, else copied, the button saying so (UX-49).
  const [link, setLink] = useState<"copied" | "refused" | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copyLink(name: string) {
    const shared = await shareLink({ title: name, text: name, url: window.location.href });
    if (shared !== "copied" && shared !== "refused") return;
    setLink(shared);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setLink(null), shared === "copied" ? 1500 : 4000);
  }

  if (searches.length === 0 && shown === null) return null;
  return (
    <section class="saved-searches" aria-labelledby="saved-searches-title">
      <h2 id="saved-searches-title" class="saved-searches__title">
        Saved searches
      </h2>
      {/* Saved, it says so quietly and keeps the focus; pressed again, it forgets it. */}
      {shown !== null && (
        <div class="saved-searches__actions">
          <button
            type="button"
            class={`link-button${savedShown ? " saved-searches__saved" : ""}`}
            aria-pressed={Boolean(savedShown)}
            title={savedShown ? "Saved: press again to remove it" : undefined}
            onClick={() => (savedShown ? onRemove(savedShown) : onSave())}
          >
            {savedShown ? (
              <>
                <CheckIcon />
                Saved
              </>
            ) : (
              "Save this search"
            )}
          </button>
          <button
            type="button"
            class="link-button saved-searches__link"
            title="Copy a link to this search: whoever opens it sees the same words, filters and period"
            onClick={() => copyLink(shown.name)}
          >
            {link === "copied" ? <CheckIcon /> : <LinkIcon />}
            {link === "copied"
              ? "Link copied"
              : link === "refused"
                ? "Copy it from the address bar"
                : "Copy link"}
          </button>
        </div>
      )}
      {searches.length > 0 && (
        <ul class="saved-searches__list">
          {searches.map((saved, position) => {
            const count = counts[position];
            return (
              <li
                key={saved.search}
                class={saved.search === added ? "saved-searches__added" : undefined}
              >
                {/* The search shown, pressed, as the reading list's folder shown. */}
                <button
                  type="button"
                  class="link-button"
                  aria-pressed={saved === savedShown}
                  onClick={() => onOpen(saved, since !== null)}
                >
                  {saved.name}
                </button>
                {count !== null && count !== undefined && (
                  <>
                    {" "}
                    <span class={count && since ? "saved-searches__new" : "muted"}>
                      {count.toLocaleString(LOCALE)}
                      {since !== null ? " new" : ""}
                    </span>
                  </>
                )}
                <button
                  type="button"
                  class="saved-searches__remove"
                  aria-label={`Remove the saved search ${saved.name}`}
                  onClick={() => onRemove(saved)}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
