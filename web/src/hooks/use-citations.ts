import { useEffect, useMemo, useState } from "preact/hooks";
import { type Filed, shardsOf } from "../citations";
import { loadCitationShard } from "../data";
import type { CitationsFile } from "../types";

export interface Citations {
  counts: ReadonlyMap<string, number>;
  /** Where the counts come from, and when they were fetched. */
  source: string | null;
  asOf: string | null;
}

const NONE: Citations = { counts: new Map(), source: null, asOf: null };

/** The shards loaded, by path, for the page's lifetime; a failed one is asked for again. */
const shards = new Map<string, Promise<CitationsFile | null>>();

function loadShard(category: string, shard: string): Promise<CitationsFile | null> {
  const key = `${category}/${shard}`;
  let file = shards.get(key);
  if (file === undefined) {
    file = loadCitationShard(category, shard).catch(() => {
      shards.delete(key);
      // Citation counts are a bonus: without them, the papers still show.
      return null;
    });
    shards.set(key, file);
  }
  return file;
}

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
    Promise.all(needed.split(" ").map((shard) => loadShard(category, shard))).then((files) => {
      if (cancelled) return;
      const counts = new Map<string, number>();
      let dated: CitationsFile | null = null;
      for (const file of files) {
        if (file === null) continue;
        dated ??= file;
        for (const [arxivId, count] of Object.entries(file.counts)) counts.set(arxivId, count);
      }
      setCitations({ counts, source: dated?.source ?? null, asOf: dated?.generated_at ?? null });
    });
    return () => {
      cancelled = true;
    };
  }, [category, needed]);
  return citations;
}
