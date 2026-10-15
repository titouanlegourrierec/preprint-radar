import { formatShortDay } from "../format";

interface Props {
  /** The time-lapse's steps: days, or the last days of weeks or months (`replaySteps`). */
  days: string[];
  /** Index of the last day shown, `null` for all days. */
  cutoff: number | null;
  onCutoff: (cutoff: number | null) => void;
  playing: boolean;
  onReplay: () => void;
}

/**
 * The time-lapse, as a player at the bottom of the canvas (UX-29): Replay grows the graph
 * day by day, and the slider shows it as it was on any day. Absent for a single day.
 */
export function GraphTimeline({ days, cutoff, onCutoff, playing, onReplay }: Props) {
  if (days.length < 2) return null;
  const lastIndex = days.length - 1;
  const day = cutoff === null ? undefined : days[cutoff];
  const shown = day === undefined ? "All days" : `To ${formatShortDay(day)}`;
  return (
    <fieldset class="graph-timeline">
      <legend class="visually-hidden">Time-lapse</legend>
      <button
        type="button"
        class="graph-timeline__play"
        aria-label={playing ? "Stop the replay" : "Replay the growth"}
        title={playing ? "Stop the replay" : "Replay the growth, day by day"}
        onClick={onReplay}
      >
        <span aria-hidden="true">{playing ? "■" : "▶"}</span>
      </button>
      <input
        type="range"
        aria-label="Announced up to"
        aria-valuetext={shown}
        min={0}
        max={lastIndex}
        step={1}
        value={cutoff ?? lastIndex}
        onInput={(event) => {
          const index = Number(event.currentTarget.value);
          onCutoff(index >= lastIndex ? null : index);
        }}
      />
      <output class="graph-timeline__day">{shown}</output>
    </fieldset>
  );
}
