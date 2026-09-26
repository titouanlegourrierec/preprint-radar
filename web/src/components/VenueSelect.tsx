import { ANY_VENUE, type FacetCount } from "../search";

interface Props {
  /** Venues of the loaded papers, most frequent first. */
  venues: FacetCount[];
  value: string | null;
  onChange: (venue: string | null) => void;
}

/** Venue filter: every paper, papers accepted anywhere, or one venue. */
export function VenueSelect({ venues, value, onChange }: Props) {
  const accepted = venues.reduce((sum, venue) => sum + venue.count, 0);
  // Keep a venue from a shared link selectable even when no loaded paper has it.
  const options =
    value && value !== ANY_VENUE && !venues.some((venue) => venue.value === value)
      ? [...venues, { value, count: 0 }]
      : venues;
  return (
    <select
      value={value ?? ""}
      aria-label="Venue"
      onChange={(event) => onChange(event.currentTarget.value || null)}
    >
      <option value="">All papers</option>
      <option value={ANY_VENUE}>Accepted at a venue ({accepted})</option>
      {options.map(({ value: venue, count }) => (
        <option key={venue} value={venue}>
          {venue} ({count})
        </option>
      ))}
    </select>
  );
}
