import { useEffect, useState } from "preact/hooks";
import {
  loadSavedSearches,
  readSearches,
  SAVED_SEARCHES_KEY,
  type SavedSearch,
  type SearchOf,
  savedSearch,
  saveSavedSearches,
} from "../saved-searches";

/** The searches saved in this browser: saved, removed, imported, and followed across tabs. */
export function useSavedSearches() {
  const [searches, setSearches] = useState<SavedSearch[]>(loadSavedSearches);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === SAVED_SEARCHES_KEY) setSearches(loadSavedSearches());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const change = (update: (current: SavedSearch[]) => SavedSearch[]) =>
    setSearches((current) => {
      const next = update(current);
      saveSavedSearches(next);
      return next;
    });

  const save = (search: SearchOf) => {
    const saved = savedSearch(search);
    if (saved)
      change((current) => [...current.filter(({ search }) => search !== saved.search), saved]);
  };
  const remove = (saved: SavedSearch) =>
    change((current) => current.filter(({ search }) => search !== saved.search));

  /** Add the searches of an exported file; says how many were added. */
  const importSearches = (value: unknown): number => {
    const imported = readSearches(
      typeof value === "object" && value !== null
        ? (value as { searches?: unknown }).searches
        : null,
    );
    const known = new Set(searches.map(({ search }) => search));
    const added = imported.filter(({ search }) => !known.has(search));
    if (added.length) change((current) => [...current, ...added]);
    return added.length;
  };

  return { searches, save, remove, importSearches };
}
