/**
 * How the rows of a ranking moved when the reader ranked them otherwise (UX-62): Rankings'
 * metrics, Trends' windows. Drawn as "▲12" or "▼3" by the rank, and said to screen readers
 * where the row's name is a link.
 */

/**
 * The places each row moved between two orders of the same list, up positive; `null` for a
 * row the first order did not hold.
 */
export function rankMoves(
  before: readonly string[],
  after: readonly string[],
): ReadonlyMap<string, number | null> {
  const was = new Map(before.map((key, index) => [key, index]));
  return new Map(
    after.map((key, index) => {
      const old = was.get(key);
      return [key, old === undefined ? null : old - index];
    }),
  );
}

/** A move as the rank shows it: "▲12", "▼3", "new", nothing for a row that stayed. */
export function moveMark(move: number | null | undefined): string {
  if (move === undefined || move === 0) return "";
  if (move === null) return "new";
  return move > 0 ? `▲${move}` : `▼${-move}`;
}

/**
 * A move as screen readers hear it, after the row's name: ", up 5 places from the 90 days",
 * ", new in this list"; nothing for a row that stayed.
 */
export function moveText(move: number | null | undefined, from: string): string {
  if (move === undefined || move === 0) return "";
  if (move === null) return ", new in this list";
  const places = Math.abs(move) === 1 ? "place" : "places";
  return `, ${move > 0 ? "up" : "down"} ${Math.abs(move)} ${places} from ${from}`;
}
