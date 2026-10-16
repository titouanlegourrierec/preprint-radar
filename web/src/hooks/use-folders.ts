import { useEffect, useState } from "preact/hooks";
import {
  addFolder,
  deleteFolder,
  FOLDERS_KEY,
  type Folder,
  findFolder,
  folderName,
  loadFolders,
  mergeFolders,
  putPaper,
  readFolders,
  renameFolder,
  saveFolders,
} from "../folders";
import { countOf } from "../format";

/**
 * The reading list's folders in this browser (UX-38), following the other tabs' changes.
 * Each change is stored at once; a refused one lasts as long as the page, as the list does.
 */
export function useFolders() {
  const [folders, setFolders] = useState<Folder[]>(loadFolders);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === FOLDERS_KEY) setFolders(loadFolders());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const change = (next: (current: Folder[]) => Folder[]) => {
    setFolders((current) => {
      const changed = next(current);
      if (changed !== current) saveFolders(changed);
      return changed;
    });
  };

  return {
    folders,
    add: (name: string) => change((current) => addFolder(current, name)),
    /** Rename a folder, and give its new name; `null` when refused (empty, or another's). */
    rename: (from: string, to: string): string | null => {
      const renamed = renameFolder(folders, from, to);
      if (renamed === folders) return null;
      saveFolders(renamed);
      setFolders(renamed);
      return findFolder(renamed, folderName(to))?.name ?? null;
    },
    remove: (name: string) => change((current) => deleteFolder(current, name)),
    /** Put a paper in a folder, or in none (`null`, a paper unsaved). */
    put: (arxivId: string, name: string | null) =>
      change((current) => putPaper(current, arxivId, name)),
    /** Merge the folders of an imported file, and say how many were added. */
    importFolders: (value: unknown): string | null => {
      const imported = readFolders(
        typeof value === "object" && value !== null
          ? (value as { folders?: unknown }).folders
          : undefined,
      );
      // Over the folders drawn, not in an update, whose count would come too late to say.
      const merged = mergeFolders(folders, imported);
      if (merged.folders === folders) return null;
      saveFolders(merged.folders);
      setFolders(merged.folders);
      return merged.added > 0
        ? `${countOf(merged.added, "folder")} added`
        : "papers put in folders";
    },
  };
}
