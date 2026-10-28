import type { CountriesFile } from "../src/world";
import type { StoredPaper } from "./scholar";

/**
 * The countries of each paper's institutions from `countries.json`, in place (PROD-22): the
 * ISO codes of those with a ROR id that OpenAlex places, as the map counts them (UX-41), for
 * the site's country filter. None for a paper whose institutions the rules named, without
 * an id.
 */
export function mergeCountries(papers: StoredPaper[], countries: CountriesFile): void {
  for (const paper of papers) {
    const codes = (paper.institution_ids ?? []).flatMap((id) => {
      const code = id === null ? undefined : countries.institutions[id];
      return code ? [code] : [];
    });
    if (codes.length > 0) paper.countries = [...new Set(codes)];
  }
}
