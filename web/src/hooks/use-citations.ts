import { useEffect, useState } from "preact/hooks";
import { loadCitations } from "../data";

export interface Citations {
  counts: ReadonlyMap<string, number>;
  /** Where the counts come from, and when they were fetched. */
  source: string | null;
  asOf: string | null;
}

const NONE: Citations = { counts: new Map(), source: null, asOf: null };

/** Citation counts of the stored papers of a category, loaded once per category. */
export function useCitations(category: string | undefined): Citations {
  const [citations, setCitations] = useState<Citations>(NONE);
  useEffect(() => {
    if (!category) return;
    let cancelled = false;
    loadCitations(category)
      .then((file) => {
        if (cancelled) return;
        setCitations(
          file
            ? {
                counts: new Map(Object.entries(file.counts)),
                source: file.source,
                asOf: file.generated_at,
              }
            : NONE,
        );
      })
      // Citation counts are a bonus: without them, the papers still show.
      .catch(() => !cancelled && setCitations(NONE));
    return () => {
      cancelled = true;
    };
  }, [category]);
  return citations;
}
