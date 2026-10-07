export interface LinkOut {
  name: string;
  url: string;
  /** What the reader finds there, for the link's tooltip. */
  title: string;
}

/**
 * Where to look for related work from a paper, by its arXiv id (SRCH-11): tools that
 * already do it, rather than a weaker copy here. Each address was opened by hand on
 * 2026-10-07, for a paper of 2017 and one of the day before. Semantic Scholar's
 * `/arxiv/<id>` is a 404 (its API redirects instead, to arXiv for a paper it does not
 * know yet), and Hugging Face is left out: its page of a paper is a 404 for 11 of 12
 * recent ones, which nobody submitted to it.
 */
export function linkOuts(arxivId: string): LinkOut[] {
  return [
    {
      name: "Semantic Scholar",
      url: `https://api.semanticscholar.org/arXiv:${arxivId}`,
      title: "Its references and the papers citing it, on Semantic Scholar",
    },
    {
      name: "Connected Papers",
      url: `https://www.connectedpapers.com/api/redirect/arxiv/${arxivId}`,
      title: "A graph of similar papers, on Connected Papers",
    },
    {
      name: "alphaXiv",
      url: `https://www.alphaxiv.org/abs/${arxivId}`,
      title: "Questions and comments on it, on alphaXiv",
    },
  ];
}
