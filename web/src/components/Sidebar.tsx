import type { ComponentChildren } from "preact";
import { useState } from "preact/hooks";
import type { ArchiveRange } from "../archive-years";
import { subjectCode } from "../format";
import { useMediaQuery } from "../hooks/use-media-query";
import type { Period } from "../period";
import {
  activeFilterCount,
  type FacetCount,
  type NameFilter,
  type SearchFilters,
  typed,
} from "../search";
import type { ArchiveSummary, DaySummary, TopRecentSummary } from "../types";
import { ArchiveSourceSelect, YearRangePicker } from "./ArchiveYears";
import { PeriodPicker } from "./PeriodPicker";
import { VenueSelect } from "./VenueSelect";

interface Props {
  categories: string[];
  category: string;
  days: DaySummary[];
  period: Period;
  filters: SearchFilters;
  authors: FacetCount[];
  affiliations: FacetCount[];
  venues: FacetCount[];
  /** Subjects of the loaded papers, primary or cross-listed (`subjectFacets`). */
  subjects: FacetCount[];
  onCategory: (category: string) => void;
  onPeriod: (period: Period) => void;
  onFilters: (filters: SearchFilters) => void;
  /** Highly cited view: years of the archive, or its last 12 months, shown instead of the period. */
  archive?:
    | {
        years: ArchiveSummary[];
        range: ArchiveRange;
        onRange: (range: ArchiveRange) => void;
      }
    | undefined;
  /** The most cited papers of the last 12 months, once the archive keeps them (PROD-11). */
  recent?: TopRecentSummary | undefined;
  /** Date of the archive, which labels its youngest year ("2025, Jan–Oct"). */
  asOf?: Date | undefined;
  /** Shown below the filters. */
  children?: ComponentChildren;
  /** Views of either kind of papers: the recent days (`null`), archive years or its last 12 months. */
  source?:
    | {
        years: ArchiveSummary[];
        range: ArchiveRange | null;
        onRange: (range: ArchiveRange | null) => void;
      }
    | undefined;
}

function FilterInput({
  label,
  placeholder,
  value,
  suggestions,
  onChange,
}: {
  label: string;
  placeholder: string;
  value: NameFilter | null;
  suggestions: FacetCount[];
  onChange: (value: NameFilter | null) => void;
}) {
  const listId = `${label.toLowerCase()}-suggestions`;
  return (
    <label class="field">
      <span>{label}</span>
      <input
        type="search"
        list={listId}
        placeholder={placeholder}
        // A clicked name matches exactly; once edited, the text matches word prefixes.
        title={value?.exact ? "This name exactly; edit it to match the start of words" : undefined}
        value={value?.text ?? ""}
        onInput={(event) =>
          onChange(event.currentTarget.value ? typed(event.currentTarget.value) : null)
        }
      />
      <datalist id={listId}>
        {suggestions.map(({ value: suggestion }) => (
          <option key={suggestion} value={suggestion} />
        ))}
      </datalist>
    </label>
  );
}

// Wide screens always show the filters, whose summary they hide (styles.css).
const WIDE_QUERY = "(min-width: 821px)";

export function Sidebar(props: Props) {
  const { filters, onFilters } = props;
  const wide = useMediaQuery(WIDE_QUERY);
  const active = activeFilterCount(filters);
  // On phones the section starts open when a filter is set; then the reader decides. A
  // window widened past the breakpoint shows it, whatever was decided.
  const [filtersOpen, setFiltersOpen] = useState(active > 0);
  return (
    <aside class="sidebar">
      {props.categories.length > 1 && (
        <label class="field">
          <span>Category</span>
          <select
            value={props.category}
            onChange={(event) => props.onCategory(event.currentTarget.value)}
          >
            {props.categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>
      )}

      {props.source && (props.source.years.length > 0 || props.recent) && (
        <ArchiveSourceSelect
          class="field"
          years={props.source.years}
          range={props.source.range}
          onChange={props.source.onRange}
          asOf={props.asOf}
          recent={props.recent}
        />
      )}

      {props.source && props.source.range !== null ? null : props.archive ? (
        <YearRangePicker
          years={props.archive.years}
          range={props.archive.range}
          onChange={props.archive.onRange}
          recent={props.recent}
        />
      ) : (
        <div class="field">
          {/* The picker's button says it, for screen readers (UX-14). */}
          <span aria-hidden="true">Period</span>
          <PeriodPicker days={props.days} period={props.period} onChange={props.onPeriod} />
        </div>
      )}

      <details
        class="filters"
        open={wide || filtersOpen}
        onToggle={(event) => {
          if (!wide) setFiltersOpen(event.currentTarget.open);
        }}
      >
        <summary>Filters{active > 0 ? ` (${active})` : ""}</summary>
        <div class="filters__body">
          <FilterInput
            label="Author"
            placeholder="e.g. Kaiming He"
            value={filters.author}
            suggestions={props.authors}
            onChange={(author) => onFilters({ ...filters, author })}
          />
          <FilterInput
            label="Affiliation"
            placeholder="e.g. KAIST, Google"
            value={filters.affiliation}
            suggestions={props.affiliations}
            onChange={(affiliation) => onFilters({ ...filters, affiliation })}
          />

          <div class="field">
            <span aria-hidden="true">Venue</span>
            <VenueSelect
              venues={props.venues}
              value={filters.venue}
              onChange={(venue) => onFilters({ ...filters, venue })}
            />
          </div>

          <label class="toggle">
            <input
              type="checkbox"
              checked={filters.excludeCrossLists}
              onChange={(event) =>
                onFilters({ ...filters, excludeCrossLists: event.currentTarget.checked })
              }
            />
            Hide cross-lists
          </label>

          <label class="toggle">
            <input
              type="checkbox"
              checked={filters.withCode}
              onChange={(event) => onFilters({ ...filters, withCode: event.currentTarget.checked })}
            />
            With code
          </label>

          {(props.subjects.length > 1 || filters.subject) && (
            <label class="field">
              <span>Subject</span>
              <select
                value={filters.subject ?? ""}
                onChange={(event) =>
                  onFilters({ ...filters, subject: event.currentTarget.value || null })
                }
              >
                <option value="">All subjects</option>
                {/* The code ("cs.RO"), as cards show it; the URL keeps the name. */}
                {props.subjects.map(({ value, count }) => (
                  <option key={value} value={value} title={value}>
                    {subjectCode(value)} ({count.toLocaleString()})
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </details>
      {props.children}
    </aside>
  );
}
