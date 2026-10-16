import { useEffect, useState } from "preact/hooks";
import {
  addFolder,
  addPaper,
  deleteFolder,
  FOLDERS_KEY,
  type Folder,
  findFolder,
  folderName,
  forgetPaper,
  loadFolders,
  mergeFolders,
  readFolders,
  removePaper,
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
    /** Put a paper in a folder too, or take it out of one (UX-45). */
    put: (arxivId: string, name: string, inFolder: boolean) =>
      change((current) =>
        inFolder ? addPaper(current, arxivId, name) : removePaper(current, arxivId, name),
      ),
    /** Take an unsaved paper out of every folder. */
    forget: (arxivId: string) => change((current) => forgetPaper(current, arxivId)),
    /**
     * Put papers in a folder, made if there is none of that name (a shared folder's,
     * UX-46), and give the folder's name, in its case here.
     */
    merge: (folder: Folder): string => {
      const merged = mergeFolders(folders, [folder]).folders;
      if (merged !== folders) {
        saveFolders(merged);
        setFolders(merged);
      }
      return findFolder(merged, folder.name)?.name ?? folder.name;
    },
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
