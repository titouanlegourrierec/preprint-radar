import type { ComponentChildren } from "preact";
import { countryName } from "../country-names";
import { isActive, NO_FILTERS, type SearchFilters } from "../search";
import { venueLabel } from "../venues";
import { Flag } from "./Flag";

interface Props {
  filters: SearchFilters;
  onFilters: (filters: SearchFilters) => void;
}

/**
 * The filters set, as chips that remove them: on phones the Filters section is closed, and
 * a name tapped on a card would otherwise filter the list without a trace.
 */
export function ActiveFilters({ filters, onFilters }: Props) {
  // Each chip's name, the filter without it, and what precedes its name for the eye.
  const chips: [string, SearchFilters, ComponentChildren?][] = [];
  if (isActive(filters.author)) {
    chips.push([`by ${filters.author.text}`, { ...filters, author: null }]);
  }
  if (isActive(filters.affiliation)) {
    chips.push([`at ${filters.affiliation.text}`, { ...filters, affiliation: null }]);
  }
  if (filters.venue !== null) {
    chips.push([venueLabel(filters.venue), { ...filters, venue: null }]);
  }
  if (filters.country !== null) {
    chips.push([
      `in ${countryName(filters.country)}`,
      { ...filters, country: null },
      <Flag code={filters.country} />,
    ]);
  }
  if (filters.subject !== null) chips.push([filters.subject, { ...filters, subject: null }]);
  if (filters.excludeCrossLists)
    chips.push(["no cross-lists", { ...filters, excludeCrossLists: false }]);
  if (filters.withCode) chips.push(["with code", { ...filters, withCode: false }]);
  if (chips.length === 0) return null;

  return (
    <ul class="active-filters" aria-label="Filters set">
      {chips.map(([label, without, before]) => (
        <li key={label}>
          <button
            type="button"
            class="chip"
            aria-label={`Remove the filter ${label}`}
            onClick={() => onFilters(without)}
          >
            {before}
            {label} <span aria-hidden="true">×</span>
          </button>
        </li>
      ))}
      {chips.length > 1 && (
        <li>
          <button type="button" class="link-button" onClick={() => onFilters(NO_FILTERS)}>
            Clear all
          </button>
        </li>
      )}
    </ul>
  );
}
