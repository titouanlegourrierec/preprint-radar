import { countOf } from "./format";
import { linkify } from "./linkify";
import type { CodeStats, Paper } from "./types";

// A repository: an owner and a name on a code host. A user's page or a project page
// (`*.github.io`) is not one.
const REPOSITORY_RE = /^https?:\/\/(?:www\.)?(?:github\.com|gitlab\.com)\/[^/?#]+\/[^/?#]+/i;
// Models, data or a demo on the Hugging Face Hub (`datasets/…`, `spaces/…`, `<owner>/<model>`),
// not the Hub's page of the paper (`papers/2610.01234`).
const HUB_RE = /^https?:\/\/(?:www\.)?huggingface\.co\/(?!papers\/)[^/?#]+\/[^/?#]+/i;

const found = new WeakMap<object, string | null>();

/**
 * The paper's code, from the links of its abstract and comments: its first repository on
 * GitHub or GitLab, else its models or data on Hugging Face; `null` when it links none.
 * About one paper in five (918 of 4,832 in October 2026), nearly all "Code is available
 * at": a library a paper builds on is seldom linked. Kept per record, since the filter
 * asks again at each search. A search shard's record has no abstract nor comments: the
 * build found its code before (`code_url`).
 */
export function codeUrl(paper: Pick<Paper, "abstract" | "comments" | "code_url">): string | null {
  if (paper.code_url !== undefined) return paper.code_url;
  let url = found.get(paper);
  if (url === undefined) {
    const urls = [paper.abstract, paper.comments].flatMap((text) =>
      text ? linkify(text).flatMap((part) => (part.url ? [part.url] : [])) : [],
    );
    url =
      urls.find((candidate) => REPOSITORY_RE.test(candidate)) ??
      urls.find((candidate) => HUB_RE.test(candidate)) ??
      null;
    found.set(paper, url);
  }
  return url;
}

/** Where a link `codeUrl` found points: its card shows that site's logo (UX-28). */
export type CodeHost = "github" | "gitlab" | "huggingface";

/** The host of a link `codeUrl` found, as the pipeline names it (`code.py`'s `code_link`). */
export function codeHost(url: string): CodeHost {
  const host = (url.split("/")[2] ?? "").toLowerCase().replace(/^www\./, "");
  return host === "github.com" ? "github" : host === "gitlab.com" ? "gitlab" : "huggingface";
}

/** How popular a paper's code is, as its card says it next to the Code link (PROD-18). */
export interface CodeBadge {
  /** The count shown after its symbol: "1,234". */
  count: string;
  /** "★" for GitHub's stars, "♥" for the Hub's likes. */
  symbol: string;
  /** What the count is, for screen readers: "GitHub stars". */
  noun: string;
  /** "+12 this week": the stars gained between the last two weekly refreshes. */
  gained: string | null;
  /** Its stars are not the paper's alone. */
  shared: boolean;
  /** The tooltip, which says all of it. */
  title: string;
}

/** The badge of a paper's code, `null` when nothing is known of it. */
export function codeBadge(stats: CodeStats | undefined): CodeBadge | null {
  if (stats?.stars !== undefined) {
    const shared = stats.shared === true;
    const gained = stats.gained ? `+${stats.gained.toLocaleString()} this week` : null;
    const sentences = [
      `${countOf(stats.stars, "star")} on GitHub, refreshed every week`,
      ...(gained ? [`${countOf(stats.gained ?? 0, "star")} gained in the last week`] : []),
      ...(shared
        ? [
            "Shared: other papers link the same repository, or this one a folder of a larger " +
              "one, so these stars are not this paper's alone",
          ]
        : []),
    ];
    return {
      count: stats.stars.toLocaleString(),
      symbol: "★",
      noun: stats.stars === 1 ? "GitHub star" : "GitHub stars",
      gained,
      shared,
      title: `${sentences.join(". ")}.`,
    };
  }
  if (stats?.likes !== undefined) {
    return {
      count: stats.likes.toLocaleString(),
      symbol: "♥",
      noun: stats.likes === 1 ? "Hugging Face like" : "Hugging Face likes",
      gained: null,
      shared: false,
      title: `${countOf(stats.likes, "like")} on Hugging Face, refreshed every week.`,
    };
  }
  return null;
}
