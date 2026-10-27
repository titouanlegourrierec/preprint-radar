import { MEDALS } from "./PaperCard";

/**
 * A row's rank in Rankings' tables (UX-60): the first three in the medals of Highly cited's
 * cards, the podium its tab draws.
 */
export function RankCell({ rank }: { rank: number }) {
  const medal = MEDALS[rank - 1];
  return (
    <td class="rankings__rank">
      {medal ? (
        <span class={`paper__rank paper__rank--${medal} rankings__medal`}>{rank}</span>
      ) : (
        rank
      )}
    </td>
  );
}

/**
 * A value's share of the first row's, for the bar under the number ranked by (UX-60), as the
 * cell's `--share` (set from code: no inline style is written as HTML).
 */
export function shareOf(value: number | null, first: number | null): string {
  const share = value !== null && first ? Math.max(0, Math.min(1, value / first)) : 0;
  return `--share: ${share.toFixed(3)}`;
}
