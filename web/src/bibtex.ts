import { fold } from "./text";
import type { Paper } from "./types";

const TITLE_STOP_WORDS = new Set(["a", "an", "the", "on", "of", "towards", "toward"]);

/** Year of submission, from the identifier (YYMM.NNNNN) when possible. */
function paperYear(paper: Paper): string {
  const match = /^(\d{2})\d{2}\./.exec(paper.arxiv_id);
  return match ? `20${match[1]}` : paper.announced.slice(0, 4);
}

function primaryClass(paper: Paper): string | null {
  return /\(([^()]+)\)\s*$/.exec(paper.primary_subject ?? "")?.[1] ?? null;
}

function slug(text: string): string {
  return fold(text).replace(/[^a-z0-9]/g, "");
}

export function citationKey(paper: Paper): string {
  const surname = paper.authors[0]?.split(/\s+/).at(-1) ?? "anonymous";
  const firstWord =
    paper.title
      .split(/\s+/)
      .map(slug)
      .find((word) => word && !TITLE_STOP_WORDS.has(word)) ?? "";
  return `${slug(surname)}${paperYear(paper)}${firstWord}`;
}

export function toBibtex(paper: Paper): string {
  const fields: [string, string | null][] = [
    ["title", paper.title],
    ["author", paper.authors.join(" and ")],
    ["year", paperYear(paper)],
    ["eprint", paper.arxiv_id],
    ["archivePrefix", "arXiv"],
    ["primaryClass", primaryClass(paper)],
    ["url", paper.abs_url],
  ];
  const body = fields
    .filter((field): field is [string, string] => field[1] !== null)
    .map(([name, value]) => `  ${name} = {${value}},`)
    .join("\n");
  return `@misc{${citationKey(paper)},\n${body}\n}`;
}

export function toBibtexFile(papers: Paper[]): string {
  return `${papers.map(toBibtex).join("\n\n")}\n`;
}
