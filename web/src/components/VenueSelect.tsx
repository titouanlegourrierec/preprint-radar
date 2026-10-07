import type { FacetCount } from "../search";
import { ANY_VENUE, familyOf, isMajorVenue, matchesVenue, sortVenues, venueLabel } from "../venues";

interface Props {
  /** Venues of the loaded papers, and their families of several editions ("CVPR*"). */
  venues: FacetCount[];
  value: string | null;
  onChange: (venue: string | null) => void;
}

function Option({ venue, starred }: { venue: FacetCount; starred: boolean }) {
  return (
    <option value={venue.value}>
      {starred ? "★ " : ""}
      {venueLabel(venue.value)} ({venue.count.toLocaleString()})
    </option>
  );
}

/**
 * Venue filter: every paper, papers accepted anywhere, every edition of a venue ("CVPR,
 * any year", SRCH-15) or one venue (major ones starred).
 */
export function VenueSelect({ venues, value, onChange }: Props) {
  // Every paper accepted somewhere, counted over all of them (`venueFacets`); the editions
  // listed are the most frequent only.
  const listed = venues.filter((venue) => venue.value !== ANY_VENUE);
  const editions = listed.filter((venue) => familyOf(venue.value) === null);
  const accepted =
    venues.find((venue) => venue.value === ANY_VENUE)?.count ??
    editions.reduce((sum, venue) => sum + venue.count, 0);
  // Keep a venue from a shared link selectable even when it is not listed: a family with
  // one edition loaded counts that edition's papers.
  const known =
    value && value !== ANY_VENUE && !listed.some((venue) => venue.value === value)
      ? [
          ...listed,
          {
            value,
            count: editions
              .filter((venue) => matchesVenue(venue.value, value))
              .reduce((sum, venue) => sum + venue.count, 0),
          },
        ]
      : listed;
  const sorted = sortVenues(known);
  const major = sorted.filter((venue) => isMajorVenue(venue.value));
  const other = sorted.filter((venue) => !isMajorVenue(venue.value));
  return (
    <select
      value={value ?? ""}
      aria-label="Venue"
      onChange={(event) => onChange(event.currentTarget.value || null)}
    >
      <option value="">All papers</option>
      <option value={ANY_VENUE}>Accepted at a venue ({accepted.toLocaleString()})</option>
      {major.length > 0 ? (
        <>
          <optgroup label="Major venues">
            {major.map((venue) => (
              <Option key={venue.value} venue={venue} starred />
            ))}
          </optgroup>
          {other.length > 0 && (
            <optgroup label="Other venues">
              {other.map((venue) => (
                <Option key={venue.value} venue={venue} starred={false} />
              ))}
            </optgroup>
          )}
        </>
      ) : (
        other.map((venue) => <Option key={venue.value} venue={venue} starred={false} />)
      )}
    </select>
  );
}
