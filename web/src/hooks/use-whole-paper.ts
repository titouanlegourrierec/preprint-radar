import { useEffect, useState } from "preact/hooks";
import { loadWholePaper } from "../data";
import type { Paper } from "../types";

export interface WholePaper {
  /** The paper whole once loaded, else the paper as given. */
  paper: Paper;
  /** Its day file is being loaded. */
  loading: boolean;
  /** Its day file could not be loaded. */
  failed: boolean;
}

/**
 * A paper whole, with its abstract and comments: itself when it was loaded whole, else,
 * once `wanted`, its record in the day file a search shard's record names (PERF-1).
 */
export function useWholePaper(paper: Paper, wanted: boolean): WholePaper {
  const [whole, setWhole] = useState<{ of: Paper; record: Paper } | null>(null);
  const [failed, setFailed] = useState<Paper | null>(null);
  const record = whole?.of === paper ? whole.record : undefined;
  const done = record !== undefined;
  useEffect(() => {
    if (paper.light === undefined || !wanted || done) return;
    let live = true;
    setFailed(null);
    loadWholePaper(paper)
      .then((found) => live && setWhole({ of: paper, record: found }))
      .catch(() => live && setFailed(paper));
    return () => {
      live = false;
    };
  }, [paper, wanted, done]);
  return {
    paper: record ?? paper,
    loading: paper.light !== undefined && wanted && !done && failed !== paper,
    failed: failed === paper,
  };
}
