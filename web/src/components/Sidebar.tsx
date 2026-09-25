import type { FacetCount, SearchFilters, SortOrder } from "../search";
import { RANGES, type RangeKey } from "../url-state";

interface Props {
  categories: string[];
  category: string;
  range: RangeKey;
  sort: SortOrder;
  filters: SearchFilters;
  affiliations: FacetCount[];
  subjects: FacetCount[];
  onCategory: (category: string) => void;
  onRange: (range: RangeKey) => void;
  onSort: (sort: SortOrder) => void;
  onFilters: (filters: SearchFilters) => void;
}

function Facet({
  title,
  counts,
  active,
  onSelect,
}: {
  title: string;
  counts: FacetCount[];
  active: string | null;
  onSelect: (value: string | null) => void;
}) {
  if (counts.length === 0) return null;
  return (
    <section class="facet">
      <h3>{title}</h3>
      <ul>
        {counts.map(({ value, count }) => (
          <li key={value}>
            <button
              type="button"
              class={`facet__item${value === active ? " facet__item--active" : ""}`}
              onClick={() => onSelect(value === active ? null : value)}
            >
              <span class="facet__label">{value}</span>
              <span class="facet__count">{count}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Sidebar(props: Props) {
  const { filters, onFilters } = props;
  return (
    <aside class="sidebar">
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

      <label class="field">
        <span>Period</span>
        <select
          value={props.range}
          onChange={(event) => props.onRange(event.currentTarget.value as RangeKey)}
        >
          {Object.entries(RANGES).map(([key, { label }]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label class="field">
        <span>Sort by</span>
        <select
          value={props.sort}
          onChange={(event) => props.onSort(event.currentTarget.value as SortOrder)}
        >
          <option value="relevance">Relevance</option>
          <option value="newest">Newest</option>
        </select>
      </label>

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

      <Facet
        title="Top affiliations"
        counts={props.affiliations}
        active={filters.affiliation}
        onSelect={(affiliation) => onFilters({ ...filters, affiliation })}
      />
      <Facet
        title="Primary subjects"
        counts={props.subjects}
        active={filters.subject}
        onSelect={(subject) => onFilters({ ...filters, subject })}
      />
    </aside>
  );
}
