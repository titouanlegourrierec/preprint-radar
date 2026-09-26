import { useEffect, useState } from "preact/hooks";
import type { SearchFilters } from "../search";
import { readState, type ViewState, writeState } from "../url-state";
import { useDebounced } from "./use-debounced";

const SEARCH_DEBOUNCE_MS = 150;

/**
 * The view state, read from the URL on load and written back on every change, so that any
 * search can be shared or bookmarked. `query` is the debounced search text: typing updates
 * `state.query` instantly, while searching and the URL wait for a pause.
 */
export function useUrlState() {
  const [state, setState] = useState<ViewState>(() => readState(window.location.search));
  const query = useDebounced(state.query, SEARCH_DEBOUNCE_MS);

  useEffect(() => {
    const url = `${window.location.pathname}${writeState({ ...state, query })}`;
    window.history.replaceState(null, "", url);
  }, [state, query]);

  const update = (patch: Partial<ViewState>) => setState((current) => ({ ...current, ...patch }));
  const setFilters = (filters: SearchFilters) => update({ filters });
  return { state, query, update, setFilters };
}
