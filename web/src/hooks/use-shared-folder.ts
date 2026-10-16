import { useEffect, useMemo, useState } from "preact/hooks";
import { loadPapersById, type StoreHolding } from "../data";
import { PaperIndex } from "../search";
import { readShare, type SharedFolder } from "../share";
import type { Paper } from "../types";

type Found =
  | { status: "loading" }
  | { status: "ready"; papers: Paper[]; missing: string[] }
  | { status: "error" };

const NONE: Paper[] = [];

const same = (a: SharedFolder | null, b: SharedFolder | null) =>
  a?.name === b?.name && a?.ids.join() === b?.ids.join();

/**
 * The folder a link shares (UX-46), from the page's fragment (`share.ts`), and its papers
 * once found in the site's data, with a search index over them as the reading list's;
 * `holding` is `null` until the store's index is loaded. A fragment pasted in the address
 * bar shares another; `close` drops it, from the address bar too.
 */
export function useSharedFolder(category: string | null, holding: StoreHolding | null) {
  const [folder, setFolder] = useState<SharedFolder | null>(() => readShare(window.location.hash));
  const [found, setFound] = useState<Found>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const onHashChange = () => {
      const next = readShare(window.location.hash);
      setFolder((current) => (same(current, next) ? current : next));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (folder === null || category === null || holding === null) return;
    let live = true;
    setFound({ status: "loading" });
    loadPapersById(category, folder.ids, holding)
      .then((result) => live && setFound({ status: "ready", ...result }))
      .catch((error: unknown) => {
        console.warn("Could not find the shared papers", error);
        if (live) setFound({ status: "error" });
      });
    return () => {
      live = false;
    };
  }, [folder, category, holding, attempt]);

  const papers = found.status === "ready" ? found.papers : NONE;
  const index = useMemo(() => new PaperIndex(papers), [papers]);
  return {
    folder,
    found,
    /** The papers found, in the link's order. */
    papers,
    index,
    retry: () => setAttempt((count) => count + 1),
    close: () => {
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
      setFolder(null);
    },
  };
}
