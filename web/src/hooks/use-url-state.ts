import { useCallback, useEffect, useState } from "preact/hooks";
import type { SearchFilters } from "../search";
import { isNavigation, readState, type ViewState, writeState } from "../url-state";
import { useDebounced } from "./use-debounced";

const SEARCH_DEBOUNCE_MS = 150;

/**
 * The view state, read from the URL on load and written back on every change, so that any
 * search can be shared or bookmarked, and the Back button undoes a step of navigation. `query` is the debounced search text: typing updates
 * `state.query` instantly, while searching and the URL wait for a pause.
 */
export function useUrlState() {
  const [state, setState] = useState<ViewState>(() => readState(window.location.search));
  const query = useDebounced(state.query, SEARCH_DEBOUNCE_MS);

  // A step of navigation adds a history entry, so that Back returns to the previous view;
  // typing and sorting replace the current one.
  useEffect(() => {
    const search = writeState({ ...state, query });
    if (search === window.location.search) return;
    const url = `${window.location.pathname}${search}`;
    if (isNavigation(readState(window.location.search), { ...state, query })) {
      window.history.pushState(null, "", url);
    } else {
      window.history.replaceState(null, "", url);
    }
  }, [state, query]);

  // Back and Forward: show the state of the entry, which then matches the URL (no new entry).
  useEffect(() => {
    const onPopState = () => setState(readState(window.location.search));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Any change drops the shared-paper anchor, like navigating away, unless the patch sets it.
  const update = useCallback(
    (patch: Partial<ViewState>) => setState((current) => ({ ...current, paper: null, ...patch })),
    [],
  );
  const setFilters = useCallback((filters: SearchFilters) => update({ filters }), [update]);
  return { state, query, update, setFilters };
}
