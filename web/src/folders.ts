/**
 * The reading list's folders (UX-38): named groups of saved papers, kept in this browser
 * apart from the papers, as the saved searches are, and exported with them. A paper is in
 * one folder at most; the stored form, each folder's ids, would take several without a
 * migration.
 */
import { arxivIdOf } from "./search";

export const FOLDERS_KEY = "preprint-radar:reading-folders";
/** What a card dragged carries (UX-39): its arXiv id, for a folder or another card. */
export const PAPER_DRAG_TYPE = "application/x-preprint-radar-paper";
/** Longer names are cut: a folder's name is a few words, shown in the sidebar and a select. */
export const MAX_FOLDER_NAME = 60;

export interface Folder {
  name: string;
  /** The arXiv ids of its papers, the latest put first. */
  papers: string[];
}

/** A name as typed, its spaces trimmed and collapsed, cut to {@link MAX_FOLDER_NAME}. */
export function folderName(text: string): string {
  return text.trim().replace(/\s+/g, " ").slice(0, MAX_FOLDER_NAME).trim();
}

/** Names that differ only in case are the same folder: "To read" and "to read". */
function sameName(a: string, b: string): boolean {
  return a.toLocaleLowerCase() === b.toLocaleLowerCase();
}

/** The folder of this name, whatever its case; `undefined` when there is none. */
export function findFolder(folders: readonly Folder[], name: string | null): Folder | undefined {
  return name === null ? undefined : folders.find((folder) => sameName(folder.name, name));
}

/** The name of the folder holding a paper, `null` when none does. */
export function folderOf(folders: readonly Folder[], arxivId: string): string | null {
  return folders.find((folder) => folder.papers.includes(arxivId))?.name ?? null;
}

/**
 * The folders of a stored value or an imported file, which are untrusted: entries that are
 * not folders are skipped, names are cleaned and kept once, ids kept when they are arXiv
 * ids, and a paper in the first folder that holds it only.
 */
export function readFolders(value: unknown): Folder[] {
  if (!Array.isArray(value)) return [];
  const folders: Folder[] = [];
  const placed = new Set<string>();
  for (const entry of value) {
    if (typeof entry !== "object" || entry === null) continue;
    const { name, papers } = entry as Record<string, unknown>;
    const cleaned = typeof name === "string" ? folderName(name) : "";
    if (cleaned === "" || findFolder(folders, cleaned)) continue;
    const ids = (Array.isArray(papers) ? papers : []).filter(
      (id): id is string => typeof id === "string" && arxivIdOf(id) === id && !placed.has(id),
    );
    for (const id of ids) placed.add(id);
    folders.push({ name: cleaned, papers: [...new Set(ids)] });
  }
  return folders;
}

/** The folders of this browser; none when the storage is empty, unreadable or refused. */
export function loadFolders(): Folder[] {
  try {
    return readFolders(JSON.parse(localStorage.getItem(FOLDERS_KEY) ?? "[]"));
  } catch {
    return [];
  }
}

/** Store the folders; `false` when the browser refused, which then keeps them for the page. */
export function saveFolders(folders: readonly Folder[]): boolean {
  try {
    localStorage.setItem(FOLDERS_KEY, JSON.stringify(folders));
    return true;
  } catch {
    return false;
  }
}

/** A new empty folder, last; the same folders when the name is empty or taken. */
export function addFolder(folders: Folder[], name: string): Folder[] {
  const cleaned = folderName(name);
  if (cleaned === "" || findFolder(folders, cleaned)) return folders;
  return [...folders, { name: cleaned, papers: [] }];
}

/**
 * A folder renamed, in its place; the same folders when the new name is empty or another
 * folder's (a change of case alone is a rename).
 */
export function renameFolder(folders: Folder[], from: string, to: string): Folder[] {
  const cleaned = folderName(to);
  const other = findFolder(folders, cleaned);
  const folder = findFolder(folders, from);
  if (cleaned === "" || folder === undefined || (other && other !== folder)) return folders;
  return folders.map((entry) => (entry === folder ? { ...entry, name: cleaned } : entry));
}

/** The folders without this one; its papers stay saved, in no folder. */
export function deleteFolder(folders: Folder[], name: string): Folder[] {
  const folder = findFolder(folders, name);
  return folder ? folders.filter((entry) => entry !== folder) : folders;
}

/**
 * A paper put in a folder, first, and out of any other; out of every folder for `null` (a
 * paper unsaved). The same folders when nothing changes.
 */
export function putPaper(folders: Folder[], arxivId: string, name: string | null): Folder[] {
  const target = findFolder(folders, name);
  if (folderOf(folders, arxivId) === (target?.name ?? null)) return folders;
  return folders.map((folder) => {
    const papers = folder.papers.filter((id) => id !== arxivId);
    return { ...folder, papers: folder === target ? [arxivId, ...papers] : papers };
  });
}

/**
 * The folders of an imported file merged into these: a folder of the same name takes the
 * file's papers that no folder holds here, a new one is added with them. How many folders
 * were added; the same array when nothing changed.
 */
export function mergeFolders(
  saved: Folder[],
  imported: readonly Folder[],
): { folders: Folder[]; added: number } {
  let folders = saved;
  let added = 0;
  for (const folder of imported) {
    if (!findFolder(folders, folder.name)) {
      folders = addFolder(folders, folder.name);
      added++;
    }
    for (const id of [...folder.papers].reverse()) {
      if (folderOf(folders, id) === null) folders = putPaper(folders, id, folder.name);
    }
  }
  return { folders, added };
}
