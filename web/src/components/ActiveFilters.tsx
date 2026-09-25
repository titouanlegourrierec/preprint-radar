import type { SearchFilters } from "../search";

interface Props {
  filters: SearchFilters;
  onFilters: (filters: SearchFilters) => void;
}

export function ActiveFilters({ filters, onFilters }: Props) {
  const active: [label: string, clear: SearchFilters][] = [];
  if (filters.author) active.push([`Author: ${filters.author}`, { ...filters, author: null }]);
  if (filters.affiliation) {
    active.push([`Affiliation: ${filters.affiliation}`, { ...filters, affiliation: null }]);
  }
  if (filters.subject) active.push([`Subject: ${filters.subject}`, { ...filters, subject: null }]);
  if (active.length === 0) return null;

  return (
    <ul class="chips active-filters" aria-label="Active filters">
      {active.map(([label, cleared]) => (
        <li key={label}>
          <button
            type="button"
            class="chip chip--removable"
            title="Remove filter"
            onClick={() => onFilters(cleared)}
          >
            {label} <span aria-hidden="true">×</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
