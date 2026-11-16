import type { ComponentChildren, ComponentProps, JSX } from "preact";
import { useState } from "preact/hooks";
import type { ArchiveRange } from "../archive-years";
import { subjectCode } from "../format";
import { useMediaQuery } from "../hooks/use-media-query";
import { LOCALE } from "../locale";
import type { Period } from "../period";
import {
  activeFilterCount,
  choiceCount,
  type FacetCount,
  isActive,
  type NameFilter,
  type SearchFilters,
  typed,
  withName,
} from "../search";
import type { ArchiveSummary, DaySummary, TopRecentSummary } from "../types";
import { venueLabel } from "../venues";
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
import { Segmented } from "./Segmented";
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
   * Every stored paper (PROD-21), a choice of the period picker beside its presets, which
   * Papers search and Rankings rank; `since`, the archive's first year.
   */
  store?:
    | { active: boolean; onChange: (active: boolean) => void; since: number | undefined }
    | undefined;
}

const MATCHES = [
  ["all", "Match all"],
  ["any", "Match any"],
] as const;

/** Chips that each remove one value of a filter, under its field (SRCH-21). */
function FilterChips({
  label,
  values,
  onRemove,
}: {
  label: string;
  values: { text: string; title: string }[];
  onRemove: (index: number) => void;
}) {
  if (values.length === 0) return null;
  return (
    <ul class="filter-chips" aria-label={`${label} filters`}>
      {values.map(({ text, title }, i) => (
        // A typed name and the same clicked share a text.
        <li key={`${i} ${text}`}>
          <button
            type="button"
            class="chip"
            title={title}
            aria-label={`Remove the ${label.toLowerCase()} ${text}`}
            onClick={() => onRemove(i)}
          >
            {text} <span aria-hidden="true">×</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/**
 * An author or affiliation filter of several names, of which a paper needs one (SRCH-21):
 * the text typed applies as it is typed, the last of the names; Enter, a suggestion chosen
 * or leaving the field keeps it, as a chip under the field, and empties the field for
 * another. Names clicked on cards join them as chips.
 */
function NamesInput({
  label,
  icon,
  example,
  values,
  suggestions,
  onChange,
}: {
  label: string;
  icon: JSX.Element;
  example: string;
  values: NameFilter[];
  suggestions: FacetCount[];
  onChange: (values: NameFilter[]) => void;
}) {
  const listId = `${label.toLowerCase()}-suggestions`;
  // The text being typed, the last name while it is: a name clicked, a chip removed or
  // another link drop it from the names, and the field shows nothing.
  const [draft, setDraft] = useState("");
  const last = values.at(-1);
  const typing = draft !== "" && last !== undefined && !last.exact && last.text === draft;
  const kept = typing ? values.slice(0, -1) : values;
  const type = (text: string) => {
    setDraft(text);
    onChange(text ? [...kept, typed(text)] : kept);
  };
  const keep = () => {
    if (!typing) return;
    setDraft("");
    // Spaces alone are no name.
    onChange(isActive(typed(draft)) ? withName(kept, typed(draft)) : kept);
  };
  return (
    <div class="names-field">
      <label class="field">
        {icon}
        <input
          type="search"
          list={listId}
          aria-label={label}
          placeholder={
            kept.length > 0 ? `or another ${label.toLowerCase()}` : `${label}, e.g. ${example}`
          }
          title={`${label}: the start of its words; Enter keeps it, for another`}
          // A suggestion chosen is kept, and only one replaces the text so (spelling
          // corrections, which would also, are off).
          autocorrect="off"
          spellcheck={false}
          value={typing ? draft : ""}
          onInput={(event) => {
            const text = event.currentTarget.value;
            if (event instanceof InputEvent && event.inputType !== "insertReplacementText") {
              type(text);
            } else if (text) {
              setDraft("");
              onChange(withName(kept, typed(text)));
            } else {
              type("");
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") keep();
          }}
          onBlur={keep}
        />
        <datalist id={listId}>
          {suggestions.map(({ value: suggestion }) => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>
      </label>
      <FilterChips
        label={label}
        values={kept.map(({ text, exact }) => ({
          text,
          title: exact ? "This name exactly" : "Names starting with these words",
        }))}
        onRemove={(index) => onChange(values.filter((_, i) => i !== index))}
      />
    </div>
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
            store={archive?.only ? undefined : store}
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
          <NamesInput
            label="Author"
            icon={<AuthorsIcon />}
            example="Kaiming He"
            values={filters.authors}
            suggestions={props.authors}
            onChange={(authors) => onFilters({ ...filters, authors })}
          />
          <NamesInput
            label="Affiliation"
            icon={<InstitutionIcon />}
            example="KAIST"
            values={filters.affiliations}
            suggestions={props.affiliations}
            onChange={(affiliations) => onFilters({ ...filters, affiliations })}
          />

          <div class="names-field">
            {/* The select names itself "Venue". */}
            <div class="field field--select">
              <VenueIcon />
              <VenueSelect
                venues={props.venues}
                values={filters.venues}
                onChange={(venues) => onFilters({ ...filters, venues })}
              />
              <SelectChevron />
            </div>
            {/* One venue the select shows; several it counts, named here. */}
            {filters.venues.length > 1 && (
              <FilterChips
                label="Venue"
                values={filters.venues.map((venue) => ({ text: venueLabel(venue), title: venue }))}
                onRemove={(index) =>
                  onFilters({ ...filters, venues: filters.venues.filter((_, i) => i !== index) })
                }
              />
            )}
          </div>

          {/* With two of the authors, affiliations and venues set: one of each, or of all. */}
          {choiceCount(filters) > 1 && (
            <Segmented
              legend="Papers matching"
              class="segmented--match"
              options={MATCHES}
              value={filters.matchAny ? "any" : "all"}
              titles={{
                all: "Papers of one of the authors, at one of the affiliations and venues",
                any: "Papers of one of the authors, affiliations or venues",
              }}
              onChange={(match) => onFilters({ ...filters, matchAny: match === "any" })}
            />
          )}

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
