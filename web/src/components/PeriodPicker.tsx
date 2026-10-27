import { useCallback, useEffect, useId, useMemo, useRef, useState } from "preact/hooks";
import { countOf } from "../format";
import { useDismiss } from "../hooks/use-dismiss";
import { LOCALE } from "../locale";
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
import { CalendarIcon, ChevronIcon, StoreIcon } from "./icons";

// Monday first: 5 January 2026 was a Monday.
const WEEKDAYS = Array.from({ length: 7 }, (_, index) =>
  new Intl.DateTimeFormat(LOCALE, { weekday: "narrow" }).format(new Date(2026, 0, 5 + index)),
);
const LONG_DAY_FORMAT = new Intl.DateTimeFormat(LOCALE, {
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

/** The recent days as one source of the papers, beside the highly cited ones (graph, Rankings). */
interface Source {
  /** Whether the recent days are what shows; the button is muted under the other source. */
  active: boolean;
  /** Picking a day or a preset shows the recent days again. */
  onActivate: () => void;
}

/**
 * The search of every stored paper (PROD-21), a choice beside the presets, which the
 * trigger then names; picking a day or a preset leaves it.
 */
interface Store {
  active: boolean;
  onChange: (active: boolean) => void;
  /** The archive's first year. */
  since: number | undefined;
}

/** How long the trigger glows once the store is chosen: its animation, and a little more. */
const LAUNCH_MS = 1600;

interface Props {
  /** Days with papers, most recent first, with their paper counts (as in the store index). */
  days: DaySummary[];
  period: Period;
  onChange: (period: Period) => void;
  source?: Source | undefined;
  store?: Store | undefined;
  /** The graph's one-line chip (UX-29), whose budget note is in the panel; else two lines. */
  compact?: boolean | undefined;
}

/**
 * Period chooser: the latest days, or a day or range of days picked on a calendar that
 * shows how many papers each day has. The first click picks a day, the second extends it
 * into a range.
 */
export function PeriodPicker({ days, period, onChange, source, store, compact }: Props) {
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
  // The store chosen: the trigger glows and its icon pops once (PROD-21), as a saved star
  // bursts (UX-37); its shimmer then goes on while it is chosen.
  const [launch, setLaunch] = useState(0);
  useEffect(() => {
    if (launch === 0) return;
    const timer = setTimeout(() => setLaunch(0), LAUNCH_MS);
    return () => clearTimeout(timer);
  }, [launch]);
  const everywhere = store?.active === true;
  // Out of sight, scrolled off or in the folded sidebar, the shimmer rests: its turning
  // border repaints every frame.
  const [inSight, setInSight] = useState(true);
  useEffect(() => {
    const trigger = triggerRef.current;
    if (!(everywhere && trigger && "IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(([entry]) =>
      setInSight(entry?.isIntersecting ?? true),
    );
    observer.observe(trigger);
    return () => observer.disconnect();
  }, [everywhere]);
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

  // Days shown as selected: the range being picked, else the current period, if shown.
  const range = anchor
    ? between(anchor, hovered ?? anchor)
    : everywhere
      ? null
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
  // A day or a preset picked while another source shows goes back to the recent days.
  const activate = () => {
    if (source && !source.active) source.onActivate();
    if (store?.active) store.onChange(false);
    setLaunch(0);
  };
  const chooseStore = () => {
    if (store && !store.active) {
      store.onChange(true);
      setLaunch((count) => count + 1);
    }
    close(true);
  };
  const pick = (day: string) => {
    activate();
    onChange(between(anchor ?? day, day));
    setAnchor(anchor ? null : day);
  };
  const choose = (key: RangeKey) => {
    activate();
    onChange({ kind: "recent", range: key });
    close(true);
  };

  // The calendar is a disclosure: a click elsewhere closes it, Escape also returns the
  // focus to its button.
  useDismiss(open, rootRef, close);

  const recentName =
    period.kind === "recent"
      ? RANGES[period.range].label
      : period.kind === "since"
        ? `Since ${formatDays(period.from, period.from)}`
        : span;
  const note = (light.length > 0 || leftOut > 0) && (
    <p class="period-picker__note">
      A period loads {PAPER_BUDGET.toLocaleString(LOCALE)} papers whole: abstracts are searched over
      its latest {countOf(whole.length, "day")}
      {light.length > 0 &&
        `, titles, authors, affiliations and venues over ${countOf(light.length, "older day")} too`}
      {leftOut > 0 &&
        `, and ${countOf(leftOut, "older day")} ${leftOut === 1 ? "is" : "are"} left out`}
      .
    </p>
  );

  return (
    <div class="period-picker" ref={rootRef}>
      <button
        type="button"
        class={`period-picker__trigger${compact ? " period-picker__trigger--chip" : ""}${
          source && !source.active ? " period-picker__trigger--muted" : ""
        }${everywhere ? " period-picker__trigger--store" : ""}${
          everywhere && launch > 0 ? " period-picker__trigger--launch" : ""
        }${everywhere && !inSight ? " period-picker__trigger--still" : ""}`}
        ref={triggerRef}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => {
          setMonth(null);
          if (open) close();
          else setOpen(true);
        }}
      >
        {everywhere ? <StoreIcon /> : <CalendarIcon />}
        <span class="visually-hidden">{compact ? "Papers: " : "Period: "}</span>
        {everywhere ? (
          <span class="period-picker__label">
            <span class="period-picker__name">All stored papers</span>
            <span class="period-picker__detail">
              {store?.since === undefined ? "Every one" : `Every one since ${store.since}`}
            </span>
          </span>
        ) : compact ? (
          <span class="period-picker__label period-picker__label--chip">
            {source?.active !== false && papers > 0
              ? `${recentName} · ${countOf(papers, "paper")}`
              : recentName}
          </span>
        ) : (
          <span class="period-picker__label">
            <span>{recentName}</span>
            <span class="period-picker__detail">
              {period.kind === "dates" ? countOf(selected.length, "day") : span} ·{" "}
              {countOf(papers, "paper")}
            </span>
          </span>
        )}
        <ChevronIcon up={open} />
      </button>
      {!compact && !everywhere && note}

      {open && (
        <div class="period-picker__panel" id={panelId}>
          <div class={`period-picker__presets${store ? " period-picker__presets--store" : ""}`}>
            {Object.entries(RANGES).map(([key, { label }]) => (
              <button
                key={key}
                type="button"
                class="chip"
                aria-pressed={
                  !everywhere &&
                  source?.active !== false &&
                  period.kind === "recent" &&
                  period.range === key
                }
                onClick={() => choose(key as RangeKey)}
              >
                {label}
              </button>
            ))}
            {store && (
              <button
                type="button"
                class="chip chip--store"
                aria-pressed={store.active}
                title={`Every paper the site stores${
                  store.since === undefined ? "" : ` since ${store.since}`
                }, whatever the period: a few seconds a search`}
                onClick={chooseStore}
              >
                <StoreIcon />
                All papers
              </button>
            )}
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
              : !everywhere && period.kind === "since"
                ? "New days join this period as they are announced. Click a day, then another one to select a range."
                : "Click a day, then another one to select a range (or use the arrows and Enter)."}
            {!anchor && !everywhere && period.kind === "dates" && period.to === latest && (
              <>
                {" "}
                <button
                  type="button"
                  class="link-button"
                  onClick={() => {
                    activate();
                    onChange({ kind: "since", from: period.from });
                    close(true);
                  }}
                >
                  Keep adding new days
                </button>
              </>
            )}
          </p>
          {compact && note}
        </div>
      )}
    </div>
  );
}
