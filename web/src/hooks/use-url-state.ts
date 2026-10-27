import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import type { SearchFilters } from "../search";
import { readShare } from "../share";
import { isNavigation, isTypedChange, readState, type ViewState, writeState } from "../url-state";
import { useDebounced } from "./use-debounced";

const SEARCH_DEBOUNCE_MS = 150;

/**
 * The view state, read from the URL on load and written back on every change, so that any
 * search can be shared or bookmarked, and the Back button undoes a step of navigation.
 * `query` and `filters` are what the search and the URL use: typing updates `state.query`
 * and the text of `state.filters` instantly, for the inputs, while searching and the URL
 * wait for a pause (PERF-4); a name clicked, a checkbox, a venue or a subject applies at
 * once (`isTypedChange`).
 */
export function useUrlState() {
  const [state, setState] = useState<ViewState>(() => readState(window.location.search));
  const query = useDebounced(state.query, SEARCH_DEBOUNCE_MS);

  // The filters last applied, which typed text leaves in place until the pause.
  const [settled, setSettled] = useState(state.filters);
  const typing = isTypedChange(settled, state.filters);
  const filters = typing ? settled : state.filters;
  useEffect(() => {
    if (!typing) {
      setSettled(state.filters);
      return;
    }
    const timer = setTimeout(() => setSettled(state.filters), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [state.filters, typing]);

  // A correction of the URL to what is shown (`correct`), which replaces its entry.
  const correcting = useRef(false);

  // A step of navigation adds a history entry, so that Back returns to the previous view;
  // typing and sorting replace the current one, and so does a correction.
  useEffect(() => {
    const applied = { ...state, query, filters };
    const search = writeState(applied);
    const corrected = correcting.current;
    correcting.current = false;
    if (search === window.location.search) return;
    // A shared folder's fragment stays while the reading list shows it (UX-46).
    const { hash } = window.location;
    const shared = applied.view === "reading-list" && readShare(hash) !== null;
    const url = `${window.location.pathname}${search}${shared ? hash : ""}`;
    if (!corrected && isNavigation(readState(window.location.search), applied)) {
      window.history.pushState(null, "", url);
    } else {
      window.history.replaceState(null, "", url);
    }
  }, [state, query, filters]);

  // Back and Forward: show the state of the entry, which then matches the URL (no new entry);
  // its filters apply at once, being no typing: else the lag would push entries over Forward.
  useEffect(() => {
    const onPopState = () => {
      const next = readState(window.location.search);
      setState(next);
      setSettled(next.filters);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Any change drops the shared-paper anchor, like navigating away, unless the patch sets it;
  // another view drops the graph's focus, which is the graph's alone, and a search of every
  // paper, the Papers view's, which a period chosen leaves too (PROD-21).
  const update = useCallback(
    (patch: Partial<ViewState>) =>
      setState((current) => {
        const next = { ...current, paper: null, ...patch };
        const scope =
          next.view === "papers" && !("period" in patch && patch.scope === undefined)
            ? next.scope
            : null;
        return { ...next, scope, focus: next.view === "graph" ? next.focus : null };
      }),
    [],
  );
  const setFilters = useCallback((next: SearchFilters) => update({ filters: next }), [update]);
  // The URL made to say what is shown, in place: no step of navigation, the paper kept.
  const correct = useCallback((patch: Partial<ViewState>) => {
    correcting.current = true;
    setState((current) => ({ ...current, ...patch }));
  }, []);
  return { state, query, filters, update, setFilters, correct };
}
