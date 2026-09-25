import type { Paper } from "../src/types";

export function makePaper(overrides: Partial<Paper> & Pick<Paper, "arxiv_id">): Paper {
  const id = overrides.arxiv_id;
  return {
    announced: "2026-09-25",
    title: `Paper ${id}`,
    authors: ["Ada Lovelace"],
    primary_subject: "Computer Vision and Pattern Recognition (cs.CV)",
    subjects: ["Computer Vision and Pattern Recognition (cs.CV)"],
    comments: null,
    journal_ref: null,
    cross_list_from: null,
    html_url: null,
    abstract: null,
    affiliations: null,
    abs_url: `https://arxiv.org/abs/${id}`,
    pdf_url: `https://arxiv.org/pdf/${id}`,
    ...overrides,
  };
}
