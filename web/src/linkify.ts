export interface TextPart {
  text: string;
  /** Set when the part is a URL. */
  url?: string;
}

const URL_RE = /https?:\/\/[^\s<>"'`]+/g;
// Punctuation that usually ends the sentence rather than the URL ("see https://x.io/y.").
const TRAILING_PUNCTUATION_RE = /[.,;:!?]+$/;

function trimUrl(candidate: string): string {
  let url = candidate.replace(TRAILING_PUNCTUATION_RE, "");
  // Drop a closing parenthesis or bracket that has no opening one inside the URL.
  while (/[)\]]$/.test(url)) {
    const close = url.at(-1) === ")" ? ")" : "]";
    const open = close === ")" ? "(" : "[";
    if (url.split(open).length >= url.split(close).length) break;
    url = url.slice(0, -1).replace(TRAILING_PUNCTUATION_RE, "");
  }
  return url;
}

/** Split text into plain parts and URL parts. */
export function linkify(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let cursor = 0;
  for (const match of text.matchAll(URL_RE)) {
    const start = match.index ?? 0;
    const url = trimUrl(match[0]);
    if (!url.replace(/^https?:\/\//, "")) continue;
    if (start > cursor) parts.push({ text: text.slice(cursor, start) });
    parts.push({ text: url, url });
    cursor = start + url.length;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor) });
  return parts;
}
