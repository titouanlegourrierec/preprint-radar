import { useState } from "preact/hooks";
import type { Period } from "../period";
import type { FacetCount, SearchFilters } from "../search";
import type { DaySummary } from "../types";
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
  subjects: FacetCount[];
  onCategory: (category: string) => void;
  onPeriod: (period: Period) => void;
  onFilters: (filters: SearchFilters) => void;
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
  value: string | null;
  suggestions: FacetCount[];
  onChange: (value: string | null) => void;
}) {
  const listId = `${label.toLowerCase()}-suggestions`;
  return (
    <label class="field">
      <span>{label}</span>
      <input
        type="search"
        list={listId}
        placeholder={placeholder}
        value={value ?? ""}
        onInput={(event) => onChange(event.currentTarget.value || null)}
      />
      <datalist id={listId}>
        {suggestions.map(({ value: suggestion }) => (
          <option key={suggestion} value={suggestion} />
        ))}
      </datalist>
    </label>
  );
}

const MOBILE_QUERY = "(max-width: 820px)";

/** Filters are always shown on wide screens; on phones, only when one is already set. */
function filtersOpenByDefault(filters: SearchFilters): boolean {
  const active = Boolean(
    filters.author ||
      filters.affiliation ||
      filters.venue ||
      filters.subject ||
      filters.excludeCrossLists,
  );
  return active || !window.matchMedia(MOBILE_QUERY).matches;
}

export function Sidebar(props: Props) {
  const { filters, onFilters } = props;
  // Computed once: afterwards the user decides whether the section stays open.
  const [filtersOpen] = useState(() => filtersOpenByDefault(filters));
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

      <div class="field">
        <span>Period</span>
        <PeriodPicker days={props.days} period={props.period} onChange={props.onPeriod} />
      </div>

      <details class="filters" open={filtersOpen}>
        <summary>Filters</summary>
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

          {(props.subjects.length > 1 || filters.subject) && (
            <label class="field">
              <span>Primary subject</span>
              <select
                value={filters.subject ?? ""}
                onChange={(event) =>
                  onFilters({ ...filters, subject: event.currentTarget.value || null })
                }
              >
                <option value="">All subjects</option>
                {props.subjects.map(({ value, count }) => (
                  <option key={value} value={value}>
                    {value} ({count})
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </details>
    </aside>
  );
}
