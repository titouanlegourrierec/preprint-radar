import { useEffect, useId, useRef, useState } from "preact/hooks";
import {
  ALL_YEARS,
  type ArchiveRange,
  LAST_12_MONTHS,
  oneYear,
  yearsIn,
  yearsLabel,
} from "../archive-years";
import { countOf } from "../format";
import type { Period } from "../period";
import type { FacetCount } from "../search";
import type { ArchiveSummary, DaySummary, TopRecentSummary } from "../types";
import { CitedIcon } from "./icons";
import { PeriodPicker } from "./PeriodPicker";
import { VenueSelect } from "./VenueSelect";

/** An award ribbon: the venue a paper was accepted at. */
function VenueIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="5.8" r="3.6" stroke="currentColor" />
      <path d="M6 8.9L4.8 14 8 12.2 11.2 14 10 8.9" stroke="currentColor" stroke-linejoin="round" />
    </svg>
  );
}

/** A funnel: the words filtering the papers. */
function WordsIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M2.5 3h11l-4.2 4.8V12l-2.6 1.7V7.8z" stroke="currentColor" stroke-linejoin="round" />
    </svg>
  );
}

/** Four tiles: the arXiv category. */
function CategoryIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M2.5 2.5h4.6v4.6H2.5zM8.9 2.5h4.6v4.6H8.9zM2.5 8.9h4.6v4.6H2.5zM8.9 8.9h4.6v4.6H8.9z"
        stroke="currentColor"
        stroke-linejoin="round"
      />
    </svg>
  );
}

interface ArchiveProps {
  /** The archive's years, newest first, as the index lists them. */
  years: ArchiveSummary[];
  /** The years shown, or the last 12 months; `null` for the recent days. */
  range: ArchiveRange | null;
  onRange: (range: ArchiveRange | null) => void;
  /** The most cited papers of the last 12 months, once the archive keeps them (PROD-11). */
  recent?: TopRecentSummary | undefined;
}

function papersIn(range: ArchiveRange, { years, recent }: ArchiveProps): number {
  if (range === LAST_12_MONTHS) return recent?.count ?? 0;
  return yearsIn(range, years).reduce((sum, year) => sum + year.count, 0);
}

/**
 * The chip of the highly cited papers: muted while the recent days show, named after the
 * years shown otherwise ("Highly cited, 2024 · 1,037 papers"). Its panel offers the last
 * 12 months, all years or one of them; the period chip goes back to the recent days.
 */
function ArchiveChip(archive: ArchiveProps) {
  const { range, onRange } = archive;
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  // A click elsewhere closes it, Escape also returns the focus to its button.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);
  const choose = (chosen: ArchiveRange) => {
    onRange(chosen);
    setOpen(false);
    triggerRef.current?.focus();
  };
  const pressed = (candidate: ArchiveRange): boolean =>
    range !== null &&
    (range === LAST_12_MONTHS || candidate === LAST_12_MONTHS
      ? range === candidate
      : range.from === candidate.from && range.to === candidate.to);

  return (
    <div class="graph-chips__source" ref={rootRef}>
      <button
        type="button"
        class={`graph-chips__chip${range === null ? " graph-chips__chip--muted" : ""}`}
        ref={triggerRef}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen(!open)}
      >
        <CitedIcon />
        <span class="graph-chips__name">
          {range === null
            ? "Highly cited"
            : `Highly cited, ${yearsLabel(range, archive.years)} · ${countOf(
                papersIn(range, archive),
                "paper",
              )}`}
        </span>
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div class="graph-chips__panel" id={panelId}>
          <p class="graph-chips__panel-label">The most cited papers, first published in</p>
          <div class="graph-chips__years">
            {archive.recent && (
              <button
                type="button"
                class="chip"
                aria-pressed={pressed(LAST_12_MONTHS)}
                onClick={() => choose(LAST_12_MONTHS)}
              >
                Last 12 months
              </button>
            )}
            {archive.years.length > 0 && (
              <button
                type="button"
                class="chip"
                aria-pressed={pressed(ALL_YEARS)}
                onClick={() => choose(ALL_YEARS)}
              >
                All years
              </button>
            )}
            {archive.years.map(({ year }) => (
              <button
                key={year}
                type="button"
                class="chip"
                aria-pressed={pressed(oneYear(year))}
                onClick={() => choose(oneYear(year))}
              >
                {year}
              </button>
            ))}
          </div>
          {range !== null && (
            <button
              type="button"
              class="chip"
              onClick={() => {
                onRange(null);
                setOpen(false);
                triggerRef.current?.focus();
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

interface Props {
  categories: string[];
  category: string;
  onCategory: (category: string) => void;
  /** Days available in the store, with paper counts. */
  storeDays: DaySummary[];
  period: Period;
  onPeriod: (period: Period) => void;
  archiveYears: ArchiveSummary[];
  /** The archive's years shown, or its last 12 months; `null` for the recent days. */
  archiveRange: ArchiveRange | null;
  onArchiveRange: (range: ArchiveRange | null) => void;
  /** The most cited papers of the last 12 months, once the archive keeps them (PROD-11). */
  topRecent?: TopRecentSummary | undefined;
  /** The words filtering the papers, typed in the Find field; a chip names and clears them. */
  query: string;
  onQuery: (query: string) => void;
  venues: FacetCount[];
  venue: string | null;
  onVenue: (venue: string | null) => void;
}

/**
 * Which papers the graph draws (UX-29), as chips floating on the canvas: the period chip
 * ("Last week · 982 papers") opens the presets and the calendar, the highly cited chip the
 * archive's years, the venue chip is the venue select, and a quoted chip names the words
 * filtering the papers, and clears them. One source shows at a time (the other chip is
 * muted); the URL keeps everything for the other views too.
 */
export function GraphFilters(props: Props) {
  const query = props.query.trim();
  return (
    <section class="graph-chips" aria-label="Papers">
      {props.categories.length > 1 && (
        <span class="graph-chips__select">
          <CategoryIcon />
          <select
            aria-label="Category"
            value={props.category}
            onChange={(event) => props.onCategory(event.currentTarget.value)}
          >
            {props.categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </span>
      )}
      <PeriodPicker
        days={props.storeDays}
        period={props.period}
        onChange={props.onPeriod}
        chip={{
          active: props.archiveRange === null,
          onActivate: () => props.onArchiveRange(null),
        }}
      />
      {(props.archiveYears.length > 0 || props.topRecent) && (
        <ArchiveChip
          years={props.archiveYears}
          range={props.archiveRange}
          onRange={props.onArchiveRange}
          recent={props.topRecent}
        />
      )}
      <span class="graph-chips__select">
        <VenueIcon />
        <VenueSelect
          venues={props.venues}
          value={props.venue}
          onChange={props.onVenue}
          allLabel="All venues"
        />
      </span>
      {query !== "" && (
        <button
          type="button"
          class="graph-chips__chip"
          aria-label={`Show all papers, not only those matching “${query}”`}
          title="Show all papers"
          onClick={() => props.onQuery("")}
        >
          <WordsIcon />
          <span class="graph-chips__name">“{query}”</span>
          <span aria-hidden="true">×</span>
        </button>
      )}
    </section>
  );
}
