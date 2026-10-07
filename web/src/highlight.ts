import { fold } from "./text";

export interface Segment {
  text: string;
  match: boolean;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** A term to highlight as a whole word only, not as the start of longer words. */
export function wholeWord(term: string): string {
  return `${term}${WHOLE_WORD}`;
}

/**
 * A term of several words to highlight as word starts, each of them: "j smith" flags
 * "John Smith", as a typed name filter keeps it. A plain term's inner words are whole,
 * as a phrase's are.
 */
export function wordStarts(term: string): string {
  return `${term}${WORD_STARTS}`;
}

const WHOLE_WORD = "\u0000";
const WORD_STARTS = "\u0001";
const BETWEEN_WORDS = "[^\\p{L}\\p{N}]+";
const REST_OF_WORD = "[\\p{L}\\p{N}]*";

function needlePattern(needle: string): string {
  const exact = needle.endsWith(WHOLE_WORD);
  const starts = needle.endsWith(WORD_STARTS);
  const words = (exact || starts ? needle.slice(0, -1) : needle).split(/\s+/).map(escapeRegExp);
  if (exact) return `${words.join(BETWEEN_WORDS)}(?![\\p{L}\\p{N}])`;
  if (starts) return words.map((word) => `${word}${REST_OF_WORD}`).join(BETWEEN_WORDS);
  return `${words.join(BETWEEN_WORDS)}${REST_OF_WORD}`;
}

/**
 * Split `text` into segments, flagging the words that start with one of `terms`, or that
 * are one of them for a term made by {@link wholeWord}.
 * Matching is accent- and case-insensitive; the original text is preserved. The words of
 * a term of several words may be separated by any punctuation, as a phrase matches them:
 * "self supervised" flags "self-supervised".
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
    `(?<![\\p{L}\\p{N}])(?:${needles.map(needlePattern).join("|")})`,
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
