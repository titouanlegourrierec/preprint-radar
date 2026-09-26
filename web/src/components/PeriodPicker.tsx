import { useMemo, useState } from "preact/hooks";
import {
  between,
  dayDate,
  formatDays,
  monthGrid,
  monthOf,
  type Period,
  RANGES,
  type RangeKey,
  selectDays,
  shiftMonth,
} from "../period";
import type { DaySummary } from "../types";

// Monday first: 5 January 2026 was a Monday.
const WEEKDAYS = Array.from({ length: 7 }, (_, index) =>
  new Intl.DateTimeFormat(undefined, { weekday: "narrow" }).format(new Date(2026, 0, 5 + index)),
);
const MONTH_FORMAT = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" });
const LONG_DAY_FORMAT = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

interface Props {
  /** Days with papers, most recent first, with their paper counts (as in the store index). */
  days: DaySummary[];
  period: Period;
  onChange: (period: Period) => void;
}

function CalendarIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.5" y="2.5" width="13" height="12" rx="2" stroke="currentColor" />
      <path d="M1.5 6.5h13M5 1v3M11 1v3" stroke="currentColor" stroke-linecap="round" />
    </svg>
  );
}

/**
 * Period chooser: the latest days, or a day or range of days picked on a calendar that
 * shows how many papers each day has. The first click picks a day, the second extends it
 * into a range.
 */
export function PeriodPicker({ days, period, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const counts = useMemo(() => new Map(days.map((day) => [day.date, day.count])), [days]);
  const maxCount = useMemo(() => Math.max(1, ...days.map((day) => day.count)), [days]);

  const selected = selectDays(days, period);
  const first = selected.at(-1)?.date;
  const last = selected[0]?.date;
  const latest = days[0]?.date ?? "";
  const earliest = days.at(-1)?.date ?? "";
  const span = first && last ? formatDays(first, last) : "No papers in this period";
  const papers = selected.reduce((sum, day) => sum + day.count, 0);

  // Days shown as selected: the range being picked, else the current period.
  const range = anchor
    ? between(anchor, hovered ?? anchor)
    : period.kind === "dates"
      ? period
      : first && last
        ? between(first, last)
        : null;
  const shown = month ?? monthOf(range?.to ?? latest);

  const close = () => {
    setOpen(false);
    setAnchor(null);
  };
  const pick = (day: string) => {
    onChange(between(anchor ?? day, day));
    setAnchor(anchor ? null : day);
  };
  const choose = (key: RangeKey) => {
    onChange({ kind: "recent", range: key });
    close();
  };

  return (
    <div class="period-picker">
      <button
        type="button"
        class="period-picker__trigger"
        aria-expanded={open}
        onClick={() => {
          setMonth(null);
          if (open) close();
          else setOpen(true);
        }}
      >
        <CalendarIcon />
        <span class="period-picker__label">
          <span>{period.kind === "recent" ? RANGES[period.range].label : span}</span>
          <span class="period-picker__detail">
            {period.kind === "recent"
              ? span
              : `${selected.length} day${selected.length === 1 ? "" : "s"}`}{" "}
            · {papers.toLocaleString()} paper{papers === 1 ? "" : "s"}
          </span>
        </span>
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <div
          class="period-picker__panel"
          role="dialog"
          aria-label="Choose the period"
          onKeyDown={(event) => event.key === "Escape" && close()}
        >
          <div class="period-picker__presets">
            {Object.entries(RANGES).map(([key, { label }]) => (
              <button
                key={key}
                type="button"
                class="chip"
                aria-pressed={period.kind === "recent" && period.range === key}
                onClick={() => choose(key as RangeKey)}
              >
                {label}
              </button>
            ))}
          </div>

          <div class="period-picker__month">
            <button
              type="button"
              aria-label="Previous month"
              disabled={shown <= monthOf(earliest)}
              onClick={() => setMonth(shiftMonth(shown, -1))}
            >
              ‹
            </button>
            <span>{MONTH_FORMAT.format(dayDate(`${shown}-01`))}</span>
            <button
              type="button"
              aria-label="Next month"
              disabled={shown >= monthOf(latest)}
              onClick={() => setMonth(shiftMonth(shown, 1))}
            >
              ›
            </button>
          </div>

          <div class="period-picker__grid">
            {WEEKDAYS.map((name, index) => (
              <span key={index} class="period-picker__weekday" aria-hidden="true">
                {name}
              </span>
            ))}
            {monthGrid(shown)
              .flat()
              .map((day, index) => {
                if (day === null) return <span key={`pad-${index}`} />;
                const count = counts.get(day);
                const inRange = range !== null && day >= range.from && day <= range.to;
                const edge = range !== null && (day === range.from || day === range.to);
                return (
                  <button
                    key={day}
                    type="button"
                    class={`period-picker__day${inRange ? " is-in-range" : ""}${edge ? " is-edge" : ""}`}
                    style={count ? `--heat: ${(count / maxCount).toFixed(2)}` : undefined}
                    disabled={count === undefined}
                    aria-pressed={inRange}
                    aria-label={`${LONG_DAY_FORMAT.format(dayDate(day))}, ${
                      count === undefined ? "no announcement" : `${count} papers`
                    }`}
                    onClick={() => pick(day)}
                    onMouseEnter={() => setHovered(day)}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <span>{Number(day.slice(8))}</span>
                    {count !== undefined && <small>{count}</small>}
                  </button>
                );
              })}
          </div>

          <p class="period-picker__summary">
            {anchor
              ? "Now click the last day of the range."
              : "Click a day, then another one to select a range."}
          </p>
        </div>
      )}
    </div>
  );
}
