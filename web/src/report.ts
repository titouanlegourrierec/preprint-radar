/**
 * Correction and removal requests go to the maintainer, privately, not in a public issue:
 * this deployment's, set at build (PUB-5); empty when it names none, and the site offers no
 * address.
 */
export const CONTACT_EMAIL: string = __CORRECTION_CONTACT__;

/** The project's repository: its code (the pipeline and this site), and its issues. */
export const REPOSITORY_URL: string = __REPOSITORY_URL__;

/** The paper a report is about. */
export interface Reported {
  arxiv_id: string;
  title: string;
}

/**
 * A `mailto:` link to report an error, with a short template to fill in: the paper's
 * title and link when there is one. The affiliations are not copied: a paper can have
 * dozens, and some mail clients (Outlook on Windows) cut links past about 2,000 characters.
 */
export function reportLink(paper?: Reported): string {
  const subject = paper
    ? `Preprint Radar: correction for arXiv:${paper.arxiv_id}`
    : "Preprint Radar: correction";
  const lines = paper
    ? [
        `Paper: ${paper.title.replace(/\s+/g, " ").trim()}`,
        `https://arxiv.org/abs/${paper.arxiv_id}`,
        "",
      ]
    : ["arXiv identifier or link of the paper:", "", ""];
  lines.push(
    "What is wrong (an author, an affiliation, an institution, the venue…), or what to remove:",
    "",
    "",
    "What it should say:",
    "",
    "",
    "How you know (the paper's first page, a homepage…), if you can say:",
    "",
  );
  // RFC 6068: line breaks in a mailto body are CRLF.
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join("\r\n"))}`;
}
