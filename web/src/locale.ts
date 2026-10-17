/**
 * The locale of every date and number the site writes (UX-17): the interface is English,
 * so a reader's own locale would mix "25 sept. 2026" or "10 000" into English sentences.
 * British English writes the day first, "25 Sept 2026", as most readers outside the
 * United States do, and the thousands with a comma, "10,000".
 */
export const LOCALE = "en-GB";
