/**
 * Lowercase and strip diacritics, so that "perez" matches "Pérez", and write ß as "ss", so
 * that "Nießner" is "Niessner" (AFF-24). Python's `institutions.search_key` folds the same
 * way, which `tests/fixtures/fold-cases.json` checks in both test suites.
 */
export function fold(text: string): string {
  return (
    text
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase()
      // Last, since the capital ẞ lowercases to ß.
      .replace(/ß/g, "ss")
  );
}

/** Name normalized for comparison: folded, punctuation collapsed to single spaces. */
export function searchKey(text: string): string {
  return fold(text)
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}
