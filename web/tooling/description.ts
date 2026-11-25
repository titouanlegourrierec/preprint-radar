import { listed } from "../src/format";

/** What index.html and the manifest say the site follows, written for cs.CV. */
export const FOLLOWED = "the cs.CV papers";

/**
 * The site's description for the categories it holds (ARCH-4): "the cs.CV papers" becomes
 * "the cs.CV and cs.LG papers". Fails on a text that does not say what it follows, so that
 * a reworded description is not left naming cs.CV alone.
 */
export function describing(text: string, categories: readonly string[]): string {
  if (!text.includes(FOLLOWED)) throw new Error(`no "${FOLLOWED}" to name the categories in`);
  if (categories.length === 0) return text;
  return text.replaceAll(FOLLOWED, `the ${listed(categories)} papers`);
}
