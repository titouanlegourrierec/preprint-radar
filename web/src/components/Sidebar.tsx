import type { ComponentChildren, ComponentProps, JSX } from "preact";
import { useState } from "preact/hooks";
import type { ArchiveRange } from "../archive-years";
import { subjectCode } from "../format";
import { useMediaQuery } from "../hooks/use-media-query";
import { LOCALE } from "../locale";
import type { Period } from "../period";
import {
  activeFilterCount,
  type FacetCount,
  type NameFilter,
  type SearchFilters,
  typed,
} from "../search";
import type { ArchiveSummary, DaySummary, TopRecentSummary } from "../types";
import type { ArchivePicker as ArchiveYearsPicker } from "./ArchiveYears";
import {
  AuthorsIcon,
  CategoryIcon,
  InstitutionIcon,
  SelectChevron,
  SidebarIcon,
  VenueIcon,
} from "./icons";
import { lazyView } from "./lazy-view";
import { PeriodPicker } from "./PeriodPicker";
import { VenueSelect } from "./VenueSelect";

// The archive's years, which the Papers list never shows, come with Highly cited or
// Rankings (PERF-15).
const ArchivePicker = lazyView<ComponentProps<typeof ArchiveYearsPicker>>(
  "highly cited years",
  () => import("./ArchiveYears").then(({ ArchivePicker }) => ArchivePicker),
  { quiet: true },
);

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
  /**
   * The archive's years, or its last 12 months: the highly cited view's papers (`only`),
   * or Rankings' other source, beside the recent days (`range` is then `null`).
   */
  archive?:
    | {
        years: ArchiveSummary[];
        range: ArchiveRange | null;
        onRange: (range: ArchiveRange | null) => void;
        only: boolean;
      }
    | undefined;
  /** The most cited papers of the last 12 months, once the archive keeps them (PROD-11). */
  recent?: TopRecentSummary | undefined;
  /** Date of the archive, which labels its youngest year ("2025, Jan–Oct"). */
  asOf?: Date | undefined;
  /** Shown below the filters. */
  children?: ComponentChildren;
  /** The reading list's folders, in place of the period it does not use (UX-38). */
  folders?: ComponentChildren;
  /**
   * The search of every stored paper (PROD-21), a choice of the period picker beside its
   * presets, in the Papers view; `since`, the archive's first year.
   */
  store?:
    | { active: boolean; onChange: (active: boolean) => void; since: number | undefined }
    | undefined;
}

function FilterInput({
  label,
  icon,
  example,
  value,
  suggestions,
  onChange,
}: {
  label: string;
  icon: JSX.Element;
  example: string;
  value: NameFilter | null;
  suggestions: FacetCount[];
  onChange: (value: NameFilter | null) => void;
}) {
  const listId = `${label.toLowerCase()}-suggestions`;
  return (
    <label class="field">
      {icon}
      <input
        type="search"
        list={listId}
        aria-label={label}
        placeholder={`${label}, e.g. ${example}`}
        // A clicked name matches exactly; once edited, the text matches word prefixes. Its
        // name says what a filled field filters, its placeholder gone.
        title={
          value?.exact ? `${label}: this name exactly; edit it to match the start of words` : label
        }
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

// Wide screens always show the filters, whose summary they hide (styles.css), and can
// fold the whole sidebar instead (UX-35).
export const WIDE_QUERY = "(min-width: 821px)";

/**
 * The button that folds the sidebar, the papers then the whole width, and shows it again
 * (UX-35): at the left of the list's count, beside the sidebar it folds. Folded, it counts
 * the filters set, which the chips above the papers name.
 */
export function SidebarToggle(props: { folded: boolean; active: number; onToggle: () => void }) {
  const label = props.folded
    ? `Show the filters${props.active > 0 ? ` (${props.active} set)` : ""}`
    : "Hide the filters";
  return (
    <button
      type="button"
      class="sidebar-toggle"
      aria-controls="sidebar"
      aria-expanded={!props.folded}
      aria-label={label}
      title={label}
      onClick={props.onToggle}
    >
      <SidebarIcon />
      {props.folded && props.active > 0 && (
        <span class="sidebar-toggle__count" aria-hidden="true">
          {props.active}
        </span>
      )}
    </button>
  );
}

export function Sidebar(props: Props) {
  const { filters, onFilters, archive, store } = props;
  const wide = useMediaQuery(WIDE_QUERY);
  const active = activeFilterCount(filters);
  // On phones the section starts open when a filter is set; then the reader decides. A
  // window widened past the breakpoint shows it, whatever was decided.
  const [filtersOpen, setFiltersOpen] = useState(active > 0);
  return (
    <aside class="sidebar" id="sidebar">
      {props.categories.length > 1 && (
        <label class="field field--select">
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
          <SelectChevron />
        </label>
      )}

      {/* The papers: the recent days, the highly cited ones, or either (Rankings), as the
          graph's chips choose them (UX-33). */}
      <div class="sidebar__papers">
        {props.folders}
        {!props.folders && !archive?.only && (
          <PeriodPicker
            days={props.days}
            period={props.period}
            onChange={props.onPeriod}
            source={
              archive && { active: archive.range === null, onActivate: () => archive.onRange(null) }
            }
            store={archive ? undefined : store}
          />
        )}
        {archive && (archive.years.length > 0 || props.recent) && (
          <ArchivePicker
            years={archive.years}
            range={archive.range}
            onRange={archive.onRange}
            recent={props.recent}
            asOf={props.asOf}
            recentDays={archive.only ? undefined : { onShow: () => archive.onRange(null) }}
          />
        )}
      </div>

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
            icon={<AuthorsIcon />}
            example="Kaiming He"
            value={filters.author}
            suggestions={props.authors}
            onChange={(author) => onFilters({ ...filters, author })}
          />
          <FilterInput
            label="Affiliation"
            icon={<InstitutionIcon />}
            example="KAIST"
            value={filters.affiliation}
            suggestions={props.affiliations}
            onChange={(affiliation) => onFilters({ ...filters, affiliation })}
          />

          {/* The select names itself "Venue". */}
          <div class="field field--select">
            <VenueIcon />
            <VenueSelect
              venues={props.venues}
              value={filters.venue}
              onChange={(venue) => onFilters({ ...filters, venue })}
            />
            <SelectChevron />
          </div>

          {(props.subjects.length > 1 || filters.subject) && (
            <label class="field field--select">
              <CategoryIcon />
              <select
                aria-label="Subject"
                value={filters.subject ?? ""}
                onChange={(event) =>
                  onFilters({ ...filters, subject: event.currentTarget.value || null })
                }
              >
                <option value="">All subjects</option>
                {/* The code ("cs.RO"), as cards show it; the URL keeps the name. */}
                {props.subjects.map(({ value, count }) => (
                  <option key={value} value={value} title={value}>
                    {subjectCode(value)} ({count.toLocaleString(LOCALE)})
                  </option>
                ))}
              </select>
              <SelectChevron />
            </label>
          )}

          {/* No "Hide cross-lists" (UX-34): too technical for a filter of its own. A link or
              saved search with `xl=0` still hides them, its chip above the papers. */}
          <label class="toggle">
            <input
              type="checkbox"
              checked={filters.withCode}
              onChange={(event) => onFilters({ ...filters, withCode: event.currentTarget.checked })}
            />
            With code
          </label>
        </div>
      </details>
      {props.children}
    </aside>
  );
}
