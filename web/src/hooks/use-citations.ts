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
  /**
   * Whether the counts are those of the papers shown: false while another period's or
   * year's stay, as the papers' own load, which an order by them waits for.
   */
  current: boolean;
}

const NONE: Citations = {
  counts: new Map(),
  source: null,
  asOf: null,
  gains: new Map(),
  gainsSpan: null,
  current: true,
};

/** A category whose counts are asked for, and its oldest day file (`citationShard`). */
export interface CitationSource {
  category: string;
  oldestDay: string | undefined;
}

/**
 * Citation counts of the papers shown (the period or archive year, and the reading list),
 * from the shards that hold them, in each category of `sources`: the reading list's papers
 * may be of any (ARCH-4), the store's records not saying theirs.
 */
export function useCitations(
  sources: readonly CitationSource[],
  papers: readonly Filed[],
): Citations {
  const [citations, setCitations] = useState<Citations>(NONE);
  // The shards whose counts `citations` holds, as "cs.CV/2026-09".
  const [loaded, setLoaded] = useState("");
  const needed = useMemo(
    () =>
      sources
        .flatMap(({ category, oldestDay }) =>
          shardsOf(papers, oldestDay).map((shard) => `${category}/${shard}`),
        )
        .join(" "),
    [sources, papers],
  );
  useEffect(() => {
    // While a period loads, the counts shown stay.
    if (!needed) return;
    let cancelled = false;
    const shards = needed.split(" ").map((path) => {
      const slash = path.indexOf("/");
      return citationShard(path.slice(0, slash), path.slice(slash + 1));
    });
    Promise.all(shards).then((files) => {
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
        current: true,
      });
      setLoaded(needed);
    });
    return () => {
      cancelled = true;
    };
  }, [needed]);
  const current = needed === "" || loaded === needed;
  return useMemo(() => ({ ...citations, current }), [citations, current]);
}
