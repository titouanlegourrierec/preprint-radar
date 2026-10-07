import { useEffect, useMemo, useState } from "preact/hooks";
import { type Filed, shardsOf } from "../citations";
import { citationShard } from "../data";
import type { CitationsFile } from "../types";

export interface Citations {
  counts: ReadonlyMap<string, number>;
  /** Where the counts come from, and when they were fetched. */
  source: string | null;
  asOf: string | null;
  /** What papers gained between the last two weekly refreshes (CIT-9), when known. */
  gains: ReadonlyMap<string, number>;
  /** The days the gains span; `null` before a second weekly refresh. */
  gainsSpan: { since: string; to: string } | null;
}

const NONE: Citations = {
  counts: new Map(),
  source: null,
  asOf: null,
  gains: new Map(),
  gainsSpan: null,
};

/**
 * Citation counts of the papers shown (the period or archive year, and the reading list),
 * from the shards that hold them. `oldestDay` is the oldest day file of the category.
 */
export function useCitations(
  category: string | undefined,
  papers: readonly Filed[],
  oldestDay: string | undefined,
): Citations {
  const [citations, setCitations] = useState<Citations>(NONE);
  const needed = useMemo(() => shardsOf(papers, oldestDay).join(" "), [papers, oldestDay]);
  useEffect(() => {
    // While a period loads, the counts shown stay.
    if (!(category && needed)) return;
    let cancelled = false;
    Promise.all(needed.split(" ").map((shard) => citationShard(category, shard))).then((files) => {
      if (cancelled) return;
      const counts = new Map<string, number>();
      const gains = new Map<string, number>();
      let dated: CitationsFile | null = null;
      for (const file of files) {
        if (file === null) continue;
        dated ??= file;
        for (const [arxivId, count] of Object.entries(file.counts)) counts.set(arxivId, count);
        for (const [arxivId, gain] of Object.entries(file.gains?.counts ?? {})) {
          gains.set(arxivId, gain);
        }
      }
      const span = dated?.gains;
      setCitations({
        counts,
        source: dated?.source ?? null,
        asOf: dated?.generated_at ?? null,
        gains,
        gainsSpan: span ? { since: span.since, to: span.to } : null,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [category, needed]);
  return citations;
}
