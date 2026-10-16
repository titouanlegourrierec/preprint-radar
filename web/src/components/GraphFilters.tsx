import type { ArchiveRange } from "../archive-years";
import type { Period } from "../period";
import type { FacetCount } from "../search";
import type { ArchiveSummary, DaySummary, TopRecentSummary } from "../types";
import { ArchivePicker } from "./ArchiveYears";
import { CategoryIcon, FilterIcon, SelectChevron, VenueIcon } from "./icons";
import { PeriodPicker } from "./PeriodPicker";
import { VenueSelect } from "./VenueSelect";

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
          <SelectChevron />
        </span>
      )}
      <PeriodPicker
        days={props.storeDays}
        period={props.period}
        onChange={props.onPeriod}
        source={{
          active: props.archiveRange === null,
          onActivate: () => props.onArchiveRange(null),
        }}
        compact
      />
      {(props.archiveYears.length > 0 || props.topRecent) && (
        <ArchivePicker
          years={props.archiveYears}
          range={props.archiveRange}
          onRange={props.onArchiveRange}
          recent={props.topRecent}
          recentDays={{ onShow: () => props.onArchiveRange(null) }}
          compact
        />
      )}
      <span class="graph-chips__select">
        <VenueIcon />
        <VenueSelect venues={props.venues} value={props.venue} onChange={props.onVenue} />
        <SelectChevron />
      </span>
      {query !== "" && (
        <button
          type="button"
          class="graph-chips__chip"
          aria-label={`Show all papers, not only those matching “${query}”`}
          title="Show all papers"
          onClick={() => props.onQuery("")}
        >
          <FilterIcon />
          <span class="graph-chips__name">“{query}”</span>
          <span aria-hidden="true">×</span>
        </button>
      )}
    </section>
  );
}
