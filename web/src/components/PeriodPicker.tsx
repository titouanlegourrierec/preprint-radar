import { useCallback, useEffect, useId, useMemo, useRef, useState } from "preact/hooks";
import { countOf } from "../format";
import {
  between,
  dayDate,
  daysOverBudget,
  formatDays,
  formatMonth,
  lightDays,
  monthGrid,
  monthOf,
  PAPER_BUDGET,
  type Period,
  RANGES,
  type RangeKey,
  selectDays,
  shiftMonth,
  stepDay,
} from "../period";
import type { DaySummary } from "../types";

// Monday first: 5 January 2026 was a Monday.
const WEEKDAYS = Array.from({ length: 7 }, (_, index) =>
  new Intl.DateTimeFormat(undefined, { weekday: "narrow" }).format(new Date(2026, 0, 5 + index)),
);
const LONG_DAY_FORMAT = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

// The days an arrow key moves the calendar's focus by.
const ARROWS: Readonly<Record<string, number>> = {
  ArrowLeft: -1,
  ArrowRight: 1,
  ArrowUp: -7,
  ArrowDown: 7,
};

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
  // The day the calendar's keyboard focus is on, which an arrow key moved (UX-14).
  const [cursor, setCursor] = useState<string | null>(null);
  // A day of another month an arrow moved to, to focus once its month is drawn.
  const focusNext = useRef<string | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const counts = useMemo(() => new Map(days.map((day) => [day.date, day.count])), [days]);
  const maxCount = useMemo(() => Math.max(1, ...days.map((day) => day.count)), [days]);

  // The latest days load whole, the older ones from the search shards (PERF-1).
  const whole = selectDays(days, period);
  const light = lightDays(days, period);
  const selected = [...whole, ...light];
  const first = selected.at(-1)?.date;
  const last = selected[0]?.date;
  const latest = days[0]?.date ?? "";
  const earliest = days.at(-1)?.date ?? "";
  const span = first && last ? formatDays(first, last) : "No papers in this period";
  const papers = selected.reduce((sum, day) => sum + day.count, 0);
  const leftOut = daysOverBudget(days, period);

  // Days shown as selected: the range being picked, else the current period.
  const range = anchor
    ? between(anchor, hovered ?? anchor)
    : period.kind === "dates"
      ? period
      : first && last
        ? between(first, last)
        : null;
  const shown = month ?? monthOf(range?.to ?? latest);
  // One day of the month shown takes Tab, the arrows the others: the day the focus was on,
  // else the period's last day, else the month's last day with papers.
  const pickable = monthGrid(shown)
    .flat()
    .filter((day): day is string => day !== null && counts.has(day));
  const tabbable =
    [cursor, range?.to].find((day) => day && pickable.includes(day)) ?? pickable.at(-1);
  const onGridKey = (event: KeyboardEvent) => {
    const step = ARROWS[event.key];
    const from = event.target instanceof HTMLElement ? event.target.dataset.day : undefined;
    if (step === undefined || from === undefined) return;
    event.preventDefault();
    const day = stepDay(from, step, (candidate) => counts.has(candidate), { earliest, latest });
    if (day === null) return;
    setCursor(day);
    const target = gridRef.current?.querySelector<HTMLElement>(`[data-day="${day}"]`);
    if (target) {
      target.focus();
      return;
    }
    focusNext.current = day;
    setMonth(monthOf(day));
  };
  // The day an arrow moved to in another month takes the focus once that month is drawn.
  useEffect(() => {
    const day = focusNext.current;
    const target = day && gridRef.current?.querySelector<HTMLElement>(`[data-day="${day}"]`);
    if (!target) return;
    focusNext.current = null;
    target.focus();
  }, [shown]);

  const close = useCallback((returnFocus = false) => {
    setOpen(false);
    setAnchor(null);
    if (returnFocus) triggerRef.current?.focus();
  }, []);
  const pick = (day: string) => {
    onChange(between(anchor ?? day, day));
    setAnchor(anchor ? null : day);
  };
  const choose = (key: RangeKey) => {
    onChange({ kind: "recent", range: key });
    close(true);
  };

  // The calendar is a disclosure: a click elsewhere closes it, Escape also returns the
  // focus to its button. Tab is free to leave it, so there is no focus trap.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        close(true);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, close]);

  return (
    <div class="period-picker" ref={rootRef}>
      <button
        type="button"
        class="period-picker__trigger"
        ref={triggerRef}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => {
          setMonth(null);
          if (open) close();
          else setOpen(true);
        }}
      >
        <CalendarIcon />
        <span class="visually-hidden">Period: </span>
        <span class="period-picker__label">
          <span>
            {period.kind === "recent"
              ? RANGES[period.range].label
              : period.kind === "since"
                ? `Since ${formatDays(period.from, period.from)}`
                : span}
          </span>
          <span class="period-picker__detail">
            {period.kind === "dates" ? countOf(selected.length, "day") : span} ·{" "}
            {countOf(papers, "paper")}
          </span>
        </span>
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {(light.length > 0 || leftOut > 0) && (
        <p class="period-picker__note">
          A period loads {PAPER_BUDGET.toLocaleString()} papers whole: abstracts are searched over
          its latest {countOf(whole.length, "day")}
          {light.length > 0 &&
            `, titles, authors, affiliations and venues over ${countOf(light.length, "older day")} too`}
          {leftOut > 0 &&
            `, and ${countOf(leftOut, "older day")} ${leftOut === 1 ? "is" : "are"} left out`}
          .
        </p>
      )}

      {open && (
        <div class="period-picker__panel" id={panelId}>
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
            <span>{formatMonth(shown)}</span>
            <button
              type="button"
              aria-label="Next month"
              disabled={shown >= monthOf(latest)}
              onClick={() => setMonth(shiftMonth(shown, 1))}
            >
              ›
            </button>
          </div>

          <div class="period-picker__grid" ref={gridRef}>
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
                    tabIndex={day === tabbable ? 0 : -1}
                    data-day={day}
                    aria-pressed={inRange}
                    aria-label={`${LONG_DAY_FORMAT.format(dayDate(day))}, ${
                      count === undefined ? "no announcement" : countOf(count, "paper")
                    }`}
                    onClick={() => pick(day)}
                    onKeyDown={onGridKey}
                    onMouseEnter={() => setHovered(day)}
                    onMouseLeave={() => setHovered(null)}
                    // The range being picked previews from the keyboard too.
                    onFocus={() => {
                      setHovered(day);
                      setCursor(day);
                    }}
                    onBlur={() => setHovered(null)}
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
              : period.kind === "since"
                ? "New days join this period as they are announced. Click a day, then another one to select a range."
                : "Click a day, then another one to select a range (or use the arrows and Enter)."}
            {!anchor && period.kind === "dates" && period.to === latest && (
              <>
                {" "}
                <button
                  type="button"
                  class="link-button"
                  onClick={() => {
                    onChange({ kind: "since", from: period.from });
                    close(true);
                  }}
                >
                  Keep adding new days
                </button>
              </>
            )}
          </p>
        </div>
      )}
    </div>
  );
}
