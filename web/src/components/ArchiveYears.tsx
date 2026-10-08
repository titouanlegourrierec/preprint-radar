import {
  ALL_YEARS,
  type ArchiveRange,
  formatYears,
  LAST_12_MONTHS,
  oneYear,
  parseYears,
  type YearRange,
  yearsIn,
  yearsLabel,
} from "../archive-years";
import { archiveYearLabel } from "../format";
import type { ArchiveSummary, TopRecentSummary } from "../types";

function yearName(year: number, asOf: Date | undefined): string {
  return asOf ? archiveYearLabel(year, asOf) : String(year);
}

function papersIn(range: YearRange, years: readonly ArchiveSummary[]): number {
  return yearsIn(range, years).reduce((sum, { count }) => sum + count, 0);
}

interface RangeProps {
  /** The archive's years, newest first, as the index lists them. */
  years: ArchiveSummary[];
  range: ArchiveRange;
  onChange: (range: ArchiveRange) => void;
  /** The most cited papers of the last 12 months, once the archive keeps them (PROD-11). */
  recent?: TopRecentSummary | undefined;
}

/**
 * The years of the highly cited view: from one year to another (the same for one year),
 * or all of them, which stays all of them as years are added; or the most cited papers of
 * the last 12 months, which the year selects leave blank. The options name the year
 * alone, for two to fit the sidebar; the view's count says how many papers, and "2025,
 * Jan–Oct".
 */
export function YearRangePicker({ years, range, onChange, recent }: RangeProps) {
  const ascending = [...years].reverse();
  const first = ascending[0]?.year ?? 0;
  const last = ascending.at(-1)?.year ?? 0;
  const lastMonths = range === LAST_12_MONTHS;
  const from = lastMonths ? null : (range.from ?? first);
  const to = lastMonths ? null : (range.to ?? last);
  const all = !lastMonths && (range.from === null || range.to === null);
  const options = [
    // Blank while the last 12 months are shown, which no year is.
    lastMonths && <option key="none" value="" disabled />,
    ...ascending.map(({ year }) => (
      <option key={year} value={year}>
        {year}
      </option>
    )),
  ];
  return (
    <fieldset class="field year-range">
      <legend>Years</legend>
      <div class="year-range__selects">
        <select
          aria-label="From the year"
          value={from ?? ""}
          onChange={(event) => {
            const year = Number(event.currentTarget.value);
            onChange(to === null ? oneYear(year) : { from: year, to: Math.max(year, to) });
          }}
        >
          {options}
        </select>
        <span aria-hidden="true">to</span>
        <select
          aria-label="To the year"
          value={to ?? ""}
          onChange={(event) => {
            const year = Number(event.currentTarget.value);
            onChange(from === null ? oneYear(year) : { from: Math.min(from, year), to: year });
          }}
        >
          {options}
        </select>
      </div>
      <button
        type="button"
        class="link-button year-range__all"
        aria-pressed={all}
        disabled={all}
        onClick={() => onChange(ALL_YEARS)}
      >
        {all ? "All years" : `All years (${papersIn(ALL_YEARS, years).toLocaleString()} papers)`}
      </button>
      {recent && (
        <button
          type="button"
          class="link-button year-range__all"
          aria-pressed={lastMonths}
          disabled={lastMonths}
          onClick={() => onChange(LAST_12_MONTHS)}
        >
          {lastMonths
            ? "Last 12 months"
            : `Last 12 months (${recent.count.toLocaleString()} papers)`}
        </button>
      )}
    </fieldset>
  );
}

interface SourceProps {
  /** The class of its label: the sidebar's field, or the graph settings' control. */
  class: string;
  years: ArchiveSummary[];
  /** The archive's years shown, or its last 12 months; `null` for the recent days. */
  range: ArchiveRange | null;
  onChange: (range: ArchiveRange | null) => void;
  asOf?: Date | undefined;
  /** The most cited papers of the last 12 months, once the archive keeps them (PROD-11). */
  recent?: TopRecentSummary | undefined;
}

/**
 * The papers of the graph or Rankings: the recent days, the most cited of the last 12
 * months, all the archive's years, one of them, or the range the highly cited view showed.
 */
export function ArchiveSourceSelect({
  class: className,
  years,
  range,
  onChange,
  asOf,
  recent,
}: SourceProps) {
  const value = range === null ? "recent" : formatYears(range);
  // A range of several years, from the highly cited view, stays selectable.
  const custom =
    range !== null &&
    range !== LAST_12_MONTHS &&
    range.from !== null &&
    range.to !== null &&
    range.from !== range.to;
  return (
    <label class={className}>
      <span>From</span>
      <select
        value={value}
        onChange={(event) => {
          const { value: chosen } = event.currentTarget;
          onChange(chosen === "recent" ? null : parseYears(chosen));
        }}
      >
        <option value="recent">Recent days</option>
        <optgroup label="Highly cited, first published in">
          {recent && (
            <option value={LAST_12_MONTHS}>
              The last 12 months ({recent.count.toLocaleString()} papers)
            </option>
          )}
          <option value="all">
            All years ({papersIn(ALL_YEARS, years).toLocaleString()} papers)
          </option>
          {custom && (
            <option value={value}>
              {yearsLabel(range, years)} ({papersIn(range, years).toLocaleString()} papers)
            </option>
          )}
          {years.map(({ year, count }) => (
            <option key={year} value={year}>
              {yearName(year, asOf)} ({count.toLocaleString()} papers)
            </option>
          ))}
        </optgroup>
      </select>
    </label>
  );
}
