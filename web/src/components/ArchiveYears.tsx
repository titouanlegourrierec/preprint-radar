import { useCallback, useId, useRef, useState } from "preact/hooks";
import {
  ALL_YEARS,
  type ArchiveRange,
  LAST_12_MONTHS,
  oneYear,
  type YearRange,
  yearsIn,
} from "../archive-years";
import { archiveYearLabel, countOf } from "../format";
import { useDismiss } from "../hooks/use-dismiss";
import type { ArchiveSummary, TopRecentSummary } from "../types";
import { ChevronIcon, CitedIcon } from "./icons";

interface Props {
  /** The archive's years, newest first, as the index lists them. */
  years: ArchiveSummary[];
  /** The years shown, or the last 12 months; `null` while the recent days show. */
  range: ArchiveRange | null;
  onRange: (range: ArchiveRange) => void;
  /** The most cited papers of the last 12 months, once the archive keeps them (PROD-11). */
  recent?: TopRecentSummary | undefined;
  /** Date of the archive, which names its youngest year ("2025, Jan–Oct"). */
  asOf?: Date | undefined;
  /**
   * The recent days, where they are the other source of the papers (the graph, Rankings):
   * the button is muted while they show, and its panel goes back to them.
   */
  recentDays?: { onShow: () => void } | undefined;
  /** The graph's one-line chip ("Highly cited, 2024 · 1,037 papers"), else two lines. */
  compact?: boolean | undefined;
}

function papersIn(
  range: ArchiveRange,
  years: readonly ArchiveSummary[],
  recent?: TopRecentSummary,
) {
  if (range === LAST_12_MONTHS) return recent?.count ?? 0;
  return yearsIn(range, years).reduce((sum, { count }) => sum + count, 0);
}

/** "2024", "2025, Jan–Oct", "2019–2021", "All years", "Last 12 months". */
function rangeName(range: ArchiveRange, years: readonly ArchiveSummary[], asOf?: Date): string {
  if (range === LAST_12_MONTHS) return "Last 12 months";
  if (range.from === null || range.to === null) return "All years";
  const shown = yearsIn(range, years);
  const first = shown.at(-1)?.year ?? range.from;
  const last = shown[0]?.year ?? range.to;
  if (first !== last) return `${first}–${last}`;
  return asOf ? archiveYearLabel(first, asOf) : String(first);
}

function isAllYears(range: ArchiveRange | null): boolean {
  return range !== null && range !== LAST_12_MONTHS && (range.from === null || range.to === null);
}

/**
 * The highly cited papers' years (UX-33): the button names the years shown and their
 * papers, and its panel, drawn as the period's calendar, offers the last 12 months, all
 * years, or a year or a range of years picked on a grid that shows each year's papers: the
 * first click picks a year, the second extends it into a range. The same in the graph's
 * chips, Rankings' sidebar beside the period, and the highly cited view's.
 */
export function ArchivePicker(props: Props) {
  const { years, range, onRange, recent, asOf, recentDays, compact } = props;
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const maxCount = Math.max(1, ...years.map(({ count }) => count));
  const ascending = [...years].reverse();

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    setAnchor(null);
    if (returnFocus) triggerRef.current?.focus();
  }, []);
  useDismiss(open, rootRef, close);

  const choose = (chosen: ArchiveRange) => {
    onRange(chosen);
    close(true);
  };
  const pick = (year: number) => {
    onRange(
      anchor === null
        ? oneYear(year)
        : { from: Math.min(anchor, year), to: Math.max(anchor, year) },
    );
    setAnchor(anchor === null ? year : null);
  };
  // Years shown as selected: the range being picked, else the one shown.
  const selected: YearRange | null =
    anchor !== null
      ? { from: Math.min(anchor, hovered ?? anchor), to: Math.max(anchor, hovered ?? anchor) }
      : range === null || range === LAST_12_MONTHS
        ? null
        : range;
  const muted = range === null && recentDays !== undefined;
  const count = range === null ? 0 : papersIn(range, years, recent);

  return (
    <div class="period-picker archive-picker" ref={rootRef}>
      <button
        type="button"
        class={`period-picker__trigger${compact ? " period-picker__trigger--chip" : ""}${
          muted ? " period-picker__trigger--muted" : ""
        }`}
        ref={triggerRef}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => (open ? close(false) : setOpen(true))}
      >
        <CitedIcon />
        {compact ? (
          <span class="period-picker__label period-picker__label--chip">
            {range === null
              ? "Highly cited"
              : `Highly cited, ${rangeName(range, years).toLowerCase()} · ${countOf(count, "paper")}`}
          </span>
        ) : (
          <span class="period-picker__label">
            <span>Highly cited</span>
            <span class="period-picker__detail">
              {range === null
                ? "By year of first version"
                : `${rangeName(range, years, asOf)} · ${countOf(count, "paper")}`}
            </span>
          </span>
        )}
        <ChevronIcon up={open} />
      </button>

      {open && (
        <div class="period-picker__panel" id={panelId}>
          <p class="period-picker__summary">The most cited papers, by year of first version</p>
          <div class="period-picker__presets">
            {recent && (
              <button
                type="button"
                class="chip"
                aria-pressed={range === LAST_12_MONTHS}
                title={countOf(recent.count, "paper")}
                onClick={() => choose(LAST_12_MONTHS)}
              >
                Last 12 months
              </button>
            )}
            {years.length > 0 && (
              <button
                type="button"
                class="chip"
                aria-pressed={isAllYears(range)}
                title={countOf(papersIn(ALL_YEARS, years), "paper")}
                onClick={() => choose(ALL_YEARS)}
              >
                All years
              </button>
            )}
          </div>

          {years.length > 0 && (
            <div class="archive-picker__grid">
              {ascending.map(({ year, count: papers }) => {
                const inRange =
                  selected !== null &&
                  (selected.from === null || year >= selected.from) &&
                  (selected.to === null || year <= selected.to);
                const edge =
                  selected !== null &&
                  selected.from !== null &&
                  (year === selected.from || year === selected.to);
                return (
                  <button
                    key={year}
                    type="button"
                    class={`period-picker__day${inRange ? " is-in-range" : ""}${edge ? " is-edge" : ""}`}
                    style={`--heat: ${(papers / maxCount).toFixed(2)}`}
                    aria-pressed={inRange}
                    aria-label={`${asOf ? archiveYearLabel(year, asOf) : year}, ${countOf(papers, "paper")}`}
                    onClick={() => pick(year)}
                    onMouseEnter={() => setHovered(year)}
                    onMouseLeave={() => setHovered(null)}
                    onFocus={() => setHovered(year)}
                    onBlur={() => setHovered(null)}
                  >
                    <span>{year}</span>
                    <small>{papers.toLocaleString()}</small>
                  </button>
                );
              })}
            </div>
          )}

          {years.length > 1 && (
            <p class="period-picker__summary">
              {anchor === null
                ? "Click a year, then another one to select a range."
                : "Now click the last year of the range."}
            </p>
          )}
          {recentDays && range !== null && (
            <button
              type="button"
              class="chip archive-picker__back"
              onClick={() => {
                recentDays.onShow();
                close(true);
              }}
            >
              Back to the recent days
            </button>
          )}
        </div>
      )}
    </div>
  );
}
