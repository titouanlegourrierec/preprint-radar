import { fold } from "./search";

export interface Segment {
  text: string;
  match: boolean;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Split `text` into segments, flagging the words that start with one of `terms`.
 * Matching is accent- and case-insensitive; the original text is preserved.
 */
export function highlight(text: string, terms: readonly string[]): Segment[] {
  const needles = [...new Set(terms.map(fold).filter((term) => term.length > 1))];
  if (needles.length === 0 || !text) return [{ text, match: false }];

  // Folding can change string length (e.g. "é" -> "e" + combining mark removed), so match on a
  // folded copy built character by character and map offsets back to the original.
  const folded: string[] = [];
  const origin: number[] = [];
  for (const [index, char] of Array.from(text).entries()) {
    // Push UTF-16 units so that regex offsets on the joined string index these arrays.
    const foldedChar = fold(char);
    for (let unit = 0; unit < foldedChar.length; unit++) {
      folded.push(foldedChar.charAt(unit));
      origin.push(index);
    }
  }
  const chars = Array.from(text);
  const pattern = new RegExp(
    `(?<![\\p{L}\\p{N}])(?:${needles.map(escapeRegExp).join("|")})[\\p{L}\\p{N}]*`,
    "gu",
  );

  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of folded.join("").matchAll(pattern)) {
    const startIndex = match.index ?? 0;
    const start = origin[startIndex] ?? 0;
    const end = (origin[startIndex + match[0].length - 1] ?? start) + 1;
    if (start > cursor) segments.push({ text: chars.slice(cursor, start).join(""), match: false });
    segments.push({ text: chars.slice(start, end).join(""), match: true });
    cursor = end;
  }
  if (cursor < chars.length) segments.push({ text: chars.slice(cursor).join(""), match: false });
  return segments;
}
