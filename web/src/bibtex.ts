import { fold } from "./text";
import type { Paper } from "./types";

const TITLE_STOP_WORDS = new Set(["a", "an", "the", "on", "of", "towards", "toward"]);
// Printed after a surname, never one: "Eduil Nascimento Jr.", "John Smith III".
const NAME_SUFFIX_RE = /^(?:jr|sr|ii|iii|iv)\.?$/i;

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

function surname(author: string | undefined): string {
  const words = (author ?? "").split(/\s+/).filter((word) => word && !NAME_SUFFIX_RE.test(word));
  return words.at(-1) ?? "anonymous";
}

/** Key of a paper's entry: first author's surname, year and first significant word. */
export function citationKey(paper: Paper): string {
  const firstWord =
    paper.title
      .split(/\s+/)
      .map(slug)
      .find((word) => word && !TITLE_STOP_WORDS.has(word)) ?? "";
  return `${slug(surname(paper.authors[0]))}${paperYear(paper)}${firstWord}`;
}

// The characters LaTeX reads as commands in text: "&" and "_" stop the compilation, "%"
// silently drops the rest of the title. Already escaped ones are left alone.
const SPECIAL_RE = /(?<!\\)([&%#_^])/g;

/**
 * Whether a word's case must survive styles that lowercase titles: an uppercase letter
 * after its first character (NeRF, CLIP, ViT, 3D, iPhone), or with a digit (R1, V2), not
 * a capitalized word.
 */
function keepsCase(word: string): boolean {
  return /\p{Lu}/u.test(word.slice(1)) || (/\d/.test(word) && /\p{Lu}/u.test(word));
}

function escapeText(text: string): string {
  return text.replace(SPECIAL_RE, (char) => (char === "^" ? "\\^{}" : `\\${char}`));
}

/**
 * A title for BibTeX: special characters escaped outside `$…$` math, and the words whose
 * case matters (acronyms, NeRF, 3D) in braces, so that sentence-case styles keep them.
 */
export function bibtexTitle(title: string): string {
  return title
    .split(/(\$[^$]*\$)/)
    .map((part, index) =>
      index % 2 === 1
        ? part
        : part
            .split(/(\s+)/)
            .map((word) => {
              const escaped = escapeText(word);
              const letters = word.replace(/[^\p{L}\p{N}-]/gu, "");
              return letters.split("-").some(keepsCase) ? `{${escaped}}` : escaped;
            })
            .join(""),
    )
    .join("");
}

/** The entry of one paper, under `key`. */
export function toBibtex(paper: Paper, key = citationKey(paper)): string {
  const fields: [string, string | null][] = [
    ["title", bibtexTitle(paper.title)],
    ["author", escapeText(paper.authors.join(" and "))],
    ["year", paperYear(paper)],
    ["eprint", paper.arxiv_id],
    ["archivePrefix", "arXiv"],
    ["primaryClass", primaryClass(paper)],
    // The published version's, when Semantic Scholar knows one; else arXiv's.
    ["doi", paper.doi ?? `10.48550/arXiv.${paper.arxiv_id}`],
    ["note", paper.venue ? escapeText(`Accepted to ${paper.venue}`) : null],
    ["url", paper.abs_url],
  ];
  const body = fields
    .filter((field): field is [string, string] => field[1] !== null)
    .map(([name, value]) => `  ${name} = {${value}},`)
    .join("\n");
  return `@misc{${key},\n${body}\n}`;
}

/**
 * The entries of several papers. Papers whose keys collide get a, b, c… in the order of
 * their identifiers: BibTeX keeps only the first of a repeated key, so both citations
 * would point at one paper.
 */
export function toBibtexFile(papers: Paper[]): string {
  const byKey = new Map<string, Paper[]>();
  for (const paper of papers) {
    const key = citationKey(paper);
    byKey.set(key, [...(byKey.get(key) ?? []), paper]);
  }
  const keys = new Map<string, string>();
  for (const [key, same] of byKey) {
    const sorted = [...same].sort((a, b) => a.arxiv_id.localeCompare(b.arxiv_id));
    sorted.forEach((paper, position) => {
      keys.set(
        paper.arxiv_id,
        same.length > 1 ? `${key}${String.fromCharCode(97 + position)}` : key,
      );
    });
  }
  return `${papers.map((paper) => toBibtex(paper, keys.get(paper.arxiv_id))).join("\n\n")}\n`;
}
