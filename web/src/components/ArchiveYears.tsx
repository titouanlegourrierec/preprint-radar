import {
  ALL_YEARS,
  formatYears,
  parseYears,
  type YearRange,
  yearsIn,
  yearsLabel,
} from "../archive-years";
import { archiveYearLabel } from "../format";
import type { ArchiveSummary } from "../types";

function yearName(year: number, asOf: Date | undefined): string {
  return asOf ? archiveYearLabel(year, asOf) : String(year);
}

function papersIn(range: YearRange, years: readonly ArchiveSummary[]): number {
  return yearsIn(range, years).reduce((sum, { count }) => sum + count, 0);
}

interface RangeProps {
  /** The archive's years, newest first, as the index lists them. */
  years: ArchiveSummary[];
  range: YearRange;
  onChange: (range: YearRange) => void;
}

/**
 * The years of the highly cited view: from one year to another (the same for one year),
 * or all of them, which stays all of them as years are added. The options name the year
 * alone, for two to fit the sidebar; the view's count says how many papers, and "2025,
 * Jan–Oct".
 */
export function YearRangePicker({ years, range, onChange }: RangeProps) {
  const ascending = [...years].reverse();
  const first = ascending[0]?.year ?? 0;
  const last = ascending.at(-1)?.year ?? 0;
  const from = range.from ?? first;
  const to = range.to ?? last;
  const all = range.from === null || range.to === null;
  const options = ascending.map(({ year }) => (
    <option key={year} value={year}>
      {year}
    </option>
  ));
  return (
    <fieldset class="field year-range">
      <legend>Years</legend>
      <div class="year-range__selects">
        <select
          aria-label="From the year"
          value={from}
          onChange={(event) => {
            const year = Number(event.currentTarget.value);
            onChange({ from: year, to: Math.max(year, to) });
          }}
        >
          {options}
        </select>
        <span aria-hidden="true">to</span>
        <select
          aria-label="To the year"
          value={to}
          onChange={(event) => {
            const year = Number(event.currentTarget.value);
            onChange({ from: Math.min(from, year), to: year });
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
    </fieldset>
  );
}

interface SourceProps {
  /** The class of its label: the sidebar's field, or the graph settings' control. */
  class: string;
  years: ArchiveSummary[];
  /** The archive's years shown, `null` for the recent days. */
  range: YearRange | null;
  onChange: (range: YearRange | null) => void;
  asOf?: Date | undefined;
}

/**
 * The papers of the graph or Rankings: the recent days, all the archive's years, one of
 * them, or the range the highly cited view showed.
 */
export function ArchiveSourceSelect({
  class: className,
  years,
  range,
  onChange,
  asOf,
}: SourceProps) {
  const value = range === null ? "recent" : formatYears(range);
  // A range of several years, from the highly cited view, stays selectable.
  const custom =
    range !== null && range.from !== null && range.to !== null && range.from !== range.to;
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
