// Letters that do not decompose into a base letter and an accent, written as plain letters
// (AFF-24), as the pipeline compares names (`institutions.PLAIN_LETTERS`).
const PLAIN_LETTERS: readonly (readonly [RegExp, string])[] = [
  [/ı/g, "i"],
  [/ł/g, "l"],
  [/ø/g, "o"],
  [/đ/g, "d"],
  [/ß/g, "ss"],
  [/æ/g, "ae"],
];

const PLAIN_ASCII_RE = /^[\0-\x5d\x5f\x61-\x7f]*$/;

/**
 * Lowercase and strip diacritics, so that "perez" matches "Pérez", and write the letters
 * that keep a stroke or a ligature plainly, so that "Nießner" is "Niessner" and "Bartłomiej"
 * is "Bartlomiej" (AFF-24). Python's `institutions.search_key` keys the cases of
 * `tests/fixtures/fold-cases.json` the same way, which both test suites check.
 */
export function fold(text: string): string {
  // Most text is ASCII, which only lowercases: but for "^" and "`", no ASCII character is
  // an accent or decomposes. Five times faster, for the search's side by side (SRCH-18).
  if (PLAIN_ASCII_RE.test(text)) return text.toLowerCase();
  const lowered = text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
  // Last, since capitals lowercase to these (ẞ to ß, Ł to ł).
  return PLAIN_LETTERS.reduce((folded, [letter, plain]) => folded.replace(letter, plain), lowered);
}

/** Name normalized for comparison: folded, punctuation collapsed to single spaces. */
export function searchKey(text: string): string {
  return fold(text)
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}
