import { useEffect, useState } from "preact/hooks";
import { loadHideSeen, saveHideSeen } from "../preferences";
import { loadSeen, newSince, previousVisit, saveSeen } from "../triage";
import type { DaySummary } from "../types";

/**
 * Daily triage of a category: the papers marked seen (and whether to hide them), and the
 * days announced since the previous visit.
 */
export function useTriage(category: string | null, days: readonly DaySummary[]) {
  const [seen, setSeen] = useState<ReadonlySet<string>>(new Set());
  const [hideSeen, setHideSeen] = useState(loadHideSeen);
  const [previous, setPrevious] = useState<string | null>(null);
  const newestDay = days[0]?.date;

  useEffect(() => {
    setSeen(category ? loadSeen(category) : new Set());
  }, [category]);

  useEffect(() => {
    setPrevious(category && newestDay ? previousVisit(category, newestDay) : null);
  }, [category, newestDay]);

  const toggleSeen = (arxivId: string) => {
    if (!category) return;
    setSeen((current) => {
      const next = new Set(current);
      if (!next.delete(arxivId)) next.add(arxivId);
      saveSeen(category, next);
      return next;
    });
  };

  const toggleHideSeen = () => {
    setHideSeen(!hideSeen);
    saveHideSeen(!hideSeen);
  };

  return {
    seen,
    toggleSeen,
    hideSeen,
    toggleHideSeen,
    previousVisit: previous,
    sinceLastVisit: newSince(days, previous),
  };
}
