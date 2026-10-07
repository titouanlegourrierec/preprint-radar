import { linkify } from "./linkify";
import type { Paper } from "./types";

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
 * asks again at each search.
 */
export function codeUrl(paper: Pick<Paper, "abstract" | "comments">): string | null {
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
