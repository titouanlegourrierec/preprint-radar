import { useEffect, useRef, useState } from "preact/hooks";
import { type Folder, MAX_FOLDER_NAME, PAPER_DRAG_TYPE } from "../folders";
import { LOCALE } from "../locale";
import { shareLink } from "../native-share";
import { FolderIcon, LinkIcon, PlusIcon, StarIcon } from "./icons";

/**
 * A folder's name typed in place, in the list: Enter keeps it, Escape or an empty name
 * gives up, leaving the field keeps what was typed.
 */
function NameField(props: {
  label: string;
  initial: string;
  onDone: (name: string | null) => void;
}) {
  const [text, setText] = useState(props.initial);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  // Enter and leaving the field both end it: once only.
  const done = useRef(false);
  const finish = (name: string | null) => {
    if (done.current) return;
    done.current = true;
    props.onDone(name?.trim() ? name : null);
  };
  return (
    <form
      class="folder folder--editing"
      onSubmit={(event) => {
        event.preventDefault();
        finish(text);
      }}
    >
      <FolderIcon />
      <input
        ref={input}
        class="folder__input"
        aria-label={props.label}
        placeholder="Folder name"
        maxLength={MAX_FOLDER_NAME}
        value={text}
        onInput={(event) => setText(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          event.preventDefault();
          event.stopPropagation();
          finish(null);
        }}
        onBlur={() => finish(text)}
      />
    </form>
  );
}

interface Props {
  folders: Folder[];
  /** The saved papers: a folder counts those it holds. */
  savedIds: ReadonlySet<string>;
  /** The folder shown, `null` for every saved paper. */
  active: string | null;
  onSelect: (name: string | null) => void;
  onAdd: (name: string) => void;
  onRename: (from: string, to: string) => void;
  onDelete: (name: string) => void;
  /** Download a folder's papers, for another browser or someone else (UX-44). */
  onExport: (name: string) => void;
  /** The link that shares a folder's papers (UX-46); `null` when it has none. */
  shareLink: (name: string) => string | null;
  /** A folder a link shares, shown above every saved paper until added or closed (UX-46). */
  shared?: { name: string; count: number | null; shown: boolean; onShow: () => void } | undefined;
  /** A card dropped on a folder goes in it, on All saved out of its folder (UX-39). */
  onDropPaper: (name: string | null, arxivId: string) => void;
}

/** How long a folder's count bounces once a card lands on it. */
const LANDED_MS = 600;

/**
 * The reading list's folders (UX-38), in the sidebar where the other lists choose their
 * papers: every saved paper, then each folder with its count; the folder shown can be
 * renamed or deleted (its papers stay saved), and a new one added. A paper goes in a folder
 * from its card.
 */
export function Folders(props: Props) {
  const { folders, savedIds, active } = props;
  const [editing, setEditing] = useState<"new" | "rename" | null>(null);
  const [confirming, setConfirming] = useState(false);
  // A folder's link copied ("copied"), or shown to copy by hand when the clipboard refused.
  const [link, setLink] = useState<string | null>(null);
  // Another folder shown asks again before deleting, and has no link copied yet.
  useEffect(() => {
    setConfirming(false);
    setLink(null);
  }, [active]);
  useEffect(() => {
    if (link !== "copied") return;
    const timer = setTimeout(() => setLink(null), 2000);
    return () => clearTimeout(timer);
  }, [link]);
  // A phone's share sheet (UX-49), else the link copied.
  const share = async (name: string) => {
    const url = props.shareLink(name);
    if (url === null) return;
    const shared = await shareLink({
      title: `“${name}” · Preprint Radar`,
      text: `“${name}”, papers shared from Preprint Radar`,
      url,
    });
    if (shared === "copied") setLink("copied");
    else if (shared === "refused") setLink(url);
  };
  const { shared } = props;
  const count = (folder: Folder) => folder.papers.filter((id) => savedIds.has(id)).length;
  const shown = folders.find((folder) => folder.name === active);

  // The row a card is dragged over, and the one it landed on (`undefined`: none; `null`:
  // All saved), which bounces its count (UX-39).
  const [over, setOver] = useState<string | null | undefined>(undefined);
  const [landed, setLanded] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    if (landed === undefined) return;
    const timer = setTimeout(() => setLanded(undefined), LANDED_MS);
    return () => clearTimeout(timer);
  }, [landed]);
  const dropTarget = (name: string | null) => ({
    class: `folder${over === name ? " folder--drop" : ""}${landed === name ? " folder--landed" : ""}`,
    onDragOver: (event: DragEvent) => {
      if (!event.dataTransfer?.types.includes(PAPER_DRAG_TYPE)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      setOver(name);
    },
    onDragLeave: (event: DragEvent) => {
      const row = event.currentTarget;
      if (
        row instanceof Node &&
        event.relatedTarget instanceof Node &&
        row.contains(event.relatedTarget)
      )
        return;
      setOver((current) => (current === name ? undefined : current));
    },
    onDrop: (event: DragEvent) => {
      const id = event.dataTransfer?.getData(PAPER_DRAG_TYPE);
      setOver(undefined);
      if (!id) return;
      event.preventDefault();
      props.onDropPaper(name, id);
      setLanded(name);
    },
  });

  return (
    <nav class="folders" aria-label="Folders">
      <ul class="folders__list">
        {shared && (
          <li>
            <button
              type="button"
              class="folder folder--shared"
              aria-pressed={shared.shown}
              title="A folder a link shares with you: add it to your reading list, or close it"
              onClick={shared.onShow}
            >
              <LinkIcon />
              <span class="folder__name">{shared.name}</span>
              <span class="folder__tag">shared</span>
              <span class="folder__count">{shared.count?.toLocaleString(LOCALE) ?? "…"}</span>
            </button>
          </li>
        )}
        <li>
          <button
            type="button"
            {...dropTarget(null)}
            aria-pressed={active === null && !shared?.shown}
            onClick={() => props.onSelect(null)}
          >
            <StarIcon />
            <span class="folder__name">All saved</span>
            <span class="folder__count">{savedIds.size.toLocaleString(LOCALE)}</span>
          </button>
        </li>
        {folders.map((folder) => (
          <li key={folder.name}>
            {editing === "rename" && folder.name === active ? (
              <NameField
                label="The folder's new name"
                initial={folder.name}
                onDone={(name) => {
                  setEditing(null);
                  if (name !== null) props.onRename(folder.name, name);
                }}
              />
            ) : (
              <button
                type="button"
                {...dropTarget(folder.name)}
                aria-pressed={folder.name === active}
                onClick={() => props.onSelect(folder.name)}
              >
                <FolderIcon />
                <span class="folder__name">{folder.name}</span>
                <span class="folder__count">{count(folder).toLocaleString(LOCALE)}</span>
              </button>
            )}
          </li>
        ))}
        {editing === "new" && (
          <li>
            <NameField
              label="The new folder's name"
              initial=""
              onDone={(name) => {
                setEditing(null);
                if (name !== null) props.onAdd(name);
              }}
            />
          </li>
        )}
      </ul>

      {active !== null && editing === null && (
        <p class="folders__actions">
          {confirming ? (
            <>
              Delete “{active}”? Its papers stay saved.{" "}
              <button
                type="button"
                class="link-button folders__delete"
                onClick={() => props.onDelete(active)}
              >
                Delete
              </button>{" "}
              <button type="button" class="link-button" onClick={() => setConfirming(false)}>
                Cancel
              </button>
            </>
          ) : (
            <>
              <button type="button" class="link-button" onClick={() => setEditing("rename")}>
                Rename
              </button>{" "}
              ·{" "}
              {shown && count(shown) > 0 && (
                <>
                  <button
                    type="button"
                    class="link-button"
                    title="This folder's papers as a file, which Import library reads in another browser"
                    onClick={() => props.onExport(shown.name)}
                  >
                    Export
                  </button>{" "}
                  ·{" "}
                  <button
                    type="button"
                    class="link-button"
                    title="Copy a link to this folder's papers: whoever opens it can add them to their reading list"
                    onClick={() => void share(shown.name)}
                  >
                    {link === "copied" ? "Link copied" : "Share"}
                  </button>{" "}
                  ·{" "}
                </>
              )}
              <button type="button" class="link-button" onClick={() => setConfirming(true)}>
                Delete
              </button>
            </>
          )}
        </p>
      )}
      {link !== null && link !== "copied" && (
        // The clipboard refused: the link to copy by hand, selected.
        <input
          class="folders__link"
          aria-label="The folder's link, to copy"
          readOnly
          value={link}
          ref={(input) => input?.select()}
        />
      )}
      {editing !== "new" && (
        <button type="button" class="folders__add" onClick={() => setEditing("new")}>
          <PlusIcon />
          New folder
        </button>
      )}
    </nav>
  );
}
