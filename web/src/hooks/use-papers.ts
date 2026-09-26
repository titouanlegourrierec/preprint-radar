import { useEffect, useState } from "preact/hooks";
import { loadDays, loadIndex } from "../data";
import { type Period, selectDays } from "../period";
import { PaperIndex } from "../search";
import type { DaySummary, StoreIndex } from "../types";

export type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; index: PaperIndex };

/**
 * The papers of one category over a period, loaded from the store and indexed for search.
 *
 * The requested category falls back to the first one in the store when it is unknown
 * (e.g. an old link after a category was dropped).
 */
export function usePapers(requestedCategory: string | null, period: Period) {
  const [storeIndex, setStoreIndex] = useState<StoreIndex | null>(null);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    loadIndex()
      .then(setStoreIndex)
      .catch((error: unknown) => setLoad({ status: "error", message: String(error) }));
  }, []);

  const categories = storeIndex ? Object.keys(storeIndex.categories).sort() : [];
  const category =
    requestedCategory && categories.includes(requestedCategory) ? requestedCategory : categories[0];
  const storeDays: DaySummary[] = (category && storeIndex?.categories[category]) || [];

  useEffect(() => {
    if (!storeIndex) return;
    if (!category) {
      setLoad({ status: "error", message: "The data store is empty." });
      return;
    }
    const days = selectDays(storeIndex.categories[category] ?? [], period);
    let cancelled = false;
    setLoad({ status: "loading" });
    loadDays(category, days)
      .then((papers) => !cancelled && setLoad({ status: "ready", index: new PaperIndex(papers) }))
      .catch(
        (error: unknown) => !cancelled && setLoad({ status: "error", message: String(error) }),
      );
    return () => {
      cancelled = true;
    };
  }, [storeIndex, category, period]);

  return { categories, category, storeDays, load, generatedAt: storeIndex?.generated_at ?? null };
}
