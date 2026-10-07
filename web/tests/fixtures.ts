import type { Paper } from "../src/types";

/**
 * A paper as the store holds it. Unless a test says otherwise, its institutions are named
 * the way the pipeline names a plain affiliation: the part before the first comma
 * ("Inria, France" is Inria).
 */
export function makePaper(overrides: Partial<Paper> & Pick<Paper, "arxiv_id">): Paper {
  const id = overrides.arxiv_id;
  const named = overrides.affiliations?.map(
    (affiliation) => affiliation.split(",")[0]?.trim() || null,
  );
  return {
    announced: "2026-09-25",
    title: `Paper ${id}`,
    authors: ["Ada Lovelace"],
    primary_subject: "Computer Vision and Pattern Recognition (cs.CV)",
    subjects: ["Computer Vision and Pattern Recognition (cs.CV)"],
    comments: null,
    journal_ref: null,
    venue: null,
    cross_list_from: null,
    html_url: null,
    abstract: null,
    affiliations: null,
    author_affiliations: null,
    institutions: named ?? null,
    abs_url: `https://arxiv.org/abs/${id}`,
    pdf_url: `https://arxiv.org/pdf/${id}`,
    ...overrides,
  };
}
