/**
 * Exports of a list of papers, for reference managers and notes: CSV (spreadsheets), RIS
 * (Zotero, EndNote, Mendeley) and Markdown. BibTeX is `bibtex.ts`.
 */
import type { Paper } from "./types";

const CSV_COLUMNS = [
  "arxiv_id",
  "title",
  "authors",
  "affiliations",
  "announced",
  "venue",
  "doi",
  "citations",
  "url",
] as const;

function csvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

/** One row per paper; authors and affiliations joined with "; ". */
export function toCsv(papers: readonly Paper[], citations: ReadonlyMap<string, number>): string {
  const rows = papers.map((paper) =>
    [
      paper.arxiv_id,
      paper.title,
      paper.authors.join("; "),
      (paper.affiliations ?? []).join("; "),
      paper.announced,
      paper.venue ?? "",
      paper.doi ?? "",
      String(citations.get(paper.arxiv_id) ?? ""),
      paper.abs_url,
    ]
      .map(csvCell)
      .join(","),
  );
  return `${[CSV_COLUMNS.join(","), ...rows].join("\r\n")}\r\n`;
}

/** RIS records, typed as preprints (`UNPB`), with the published version's DOI, else arXiv's. */
export function toRis(papers: readonly Paper[]): string {
  return papers
    .map((paper) => {
      const lines = [
        "TY  - UNPB",
        `TI  - ${oneLine(paper.title)}`,
        ...paper.authors.map((author) => `AU  - ${author}`),
        `PY  - ${paper.announced.slice(0, 4)}`,
        `DA  - ${paper.announced.replaceAll("-", "/")}`,
        ...(paper.abstract ? [`AB  - ${oneLine(paper.abstract)}`] : []),
        `DO  - ${paper.doi ?? `10.48550/arXiv.${paper.arxiv_id}`}`,
        `UR  - ${paper.abs_url}`,
        `PB  - arXiv`,
        `M1  - arXiv:${paper.arxiv_id}`,
        ...(paper.venue ? [`N1  - Accepted to ${paper.venue}`] : []),
        "ER  - ",
      ];
      return lines.join("\r\n");
    })
    .join("\r\n\r\n")
    .concat("\r\n");
}

/** A bulleted list: linked title, then authors and arXiv identifier. */
export function toMarkdown(papers: readonly Paper[]): string {
  return papers
    .map((paper) => {
      const authors =
        paper.authors.length > 3
          ? `${paper.authors.slice(0, 3).join(", ")} et al.`
          : paper.authors.join(", ");
      const venue = paper.venue ? `, ${paper.venue}` : "";
      return `- [${oneLine(paper.title).replace(/[[\]]/g, "\\$&")}](${paper.abs_url}) — ${authors} (arXiv:${paper.arxiv_id}${venue})`;
    })
    .join("\n")
    .concat("\n");
}

function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}
