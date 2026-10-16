/**
 * A reading list folder shared by a link (UX-46): its name and its papers' arXiv ids in the
 * link's fragment, `#folder=To%20read&papers=2610.01234,2609.12345`, which the browser
 * never sends to the server; whoever opens it sees the papers, found in the site's data,
 * and can add them to their own reading list. A copy, not a folder kept in common.
 */
import { folderName } from "./folders";
import { arxivIdOf } from "./search";

/** A link holds at most this many papers: 11 kB of fragment, which any chat passes on. */
export const MAX_SHARED = 1000;

export interface SharedFolder {
  name: string;
  /** Its papers' arXiv ids, in its order, once each. */
  ids: string[];
}

/**
 * The fragment of a folder's link; its ids as they are, commas unescaped (URLSearchParams
 * would write each as `%2C`), the first {@link MAX_SHARED} only.
 */
export function shareHash(name: string, ids: readonly string[]): string {
  return `#folder=${encodeURIComponent(name)}&papers=${ids.slice(0, MAX_SHARED).join(",")}`;
}

/**
 * The folder a link's fragment shares, which is untrusted: its name cleaned (that of a new
 * folder), ids kept when they are arXiv ids, once each, without their version; `null` for
 * any other fragment, or one without a paper.
 */
export function readShare(hash: string): SharedFolder | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const papers = params.get("papers");
  if (papers === null) return null;
  const ids = [...new Set(papers.split(",").flatMap((text) => arxivIdOf(text) ?? []))].slice(
    0,
    MAX_SHARED,
  );
  if (ids.length === 0) return null;
  return { name: folderName(params.get("folder") ?? "") || "Shared papers", ids };
}

/** The year and month of an arXiv id's first version ("2609.12345": 2026, 9); `null` for an old id. */
function submitted(arxivId: string): { year: number; month: number } | null {
  const match = /^(\d{2})(\d{2})\.\d{4,5}$/.exec(arxivId);
  if (!match) return null;
  return { year: 2000 + Number(match[1]), month: Number(match[2]) };
}

/**
 * The months a paper may have been announced in ("2026-09"): that of its id, its
 * submission, or the next one, for a paper sent on the month's last days.
 */
export function candidateMonths(arxivId: string): string[] {
  const at = submitted(arxivId);
  if (at === null) return [];
  const next = at.month === 12 ? { year: at.year + 1, month: 1 } : { ...at, month: at.month + 1 };
  return [at, next].map(({ year, month }) => `${year}-${String(month).padStart(2, "0")}`);
}

/** The years of first appearance the archive may keep a paper under: its id's, or the next. */
export function candidateYears(arxivId: string): number[] {
  const at = submitted(arxivId);
  if (at === null) return [];
  return at.month === 12 ? [at.year, at.year + 1] : [at.year];
}
