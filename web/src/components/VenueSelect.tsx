import { LOCALE } from "../locale";
import { type FacetCount, withVenue } from "../search";
import { ANY_VENUE, familyOf, isMajorVenue, matchesVenue, sortVenues, venueLabel } from "../venues";

interface Props {
  /** Venues of the loaded papers, and their families of several editions ("CVPR*"). */
  venues: FacetCount[];
  /** The venues chosen, of which a paper needs one (SRCH-21). */
  values: string[];
  onChange: (venues: string[]) => void;
}

// The select's value while it shows several venues chosen: no venue is called so.
const SEVERAL = "\n";

function Option({ venue, starred }: { venue: FacetCount; starred: boolean }) {
  return (
    <option value={venue.value}>
      {starred ? "★ " : ""}
      {venueLabel(venue.value)} ({venue.count.toLocaleString(LOCALE)})
    </option>
  );
}

/**
 * Venue filter: every paper, papers accepted anywhere, every edition of a venue ("CVPR,
 * any year", SRCH-15) or one venue (major ones starred). A venue chosen is added to those
 * already chosen (SRCH-21), the select then naming how many; "All venues" clears them, and
 * the chips remove one.
 */
export function VenueSelect({ venues, values, onChange }: Props) {
  // Every paper accepted somewhere, counted over all of them (`venueFacets`); the editions
  // listed are the most frequent only.
  const listed = venues.filter((venue) => venue.value !== ANY_VENUE);
  const editions = listed.filter((venue) => familyOf(venue.value) === null);
  const accepted =
    venues.find((venue) => venue.value === ANY_VENUE)?.count ??
    editions.reduce((sum, venue) => sum + venue.count, 0);
  // Keep a venue from a shared link selectable even when it is not listed: a family with
  // one edition loaded counts that edition's papers.
  const unlisted = values.filter(
    (value) => value !== ANY_VENUE && !listed.some((venue) => venue.value === value),
  );
  const known = [
    ...listed,
    ...unlisted.map((value) => ({
      value,
      count: editions
        .filter((venue) => matchesVenue(venue.value, value))
        .reduce((sum, venue) => sum + venue.count, 0),
    })),
  ];
  const sorted = sortVenues(known);
  const major = sorted.filter((venue) => isMajorVenue(venue.value));
  const other = sorted.filter((venue) => !isMajorVenue(venue.value));
  return (
    <select
      value={values.length > 1 ? SEVERAL : (values[0] ?? "")}
      aria-label="Venue"
      onChange={(event) => {
        const { value } = event.currentTarget;
        if (value !== SEVERAL) onChange(value ? withVenue(values, value) : []);
      }}
    >
      <option value="">All venues</option>
      {values.length > 1 && (
        <option value={SEVERAL} disabled>
          {values.length} venues
        </option>
      )}
      <option value={ANY_VENUE}>Accepted at a venue ({accepted.toLocaleString(LOCALE)})</option>
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
