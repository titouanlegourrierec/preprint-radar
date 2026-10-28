/**
 * Countries by name (PROD-22): the country filter takes ISO codes ("FR"), as the build
 * writes them, and people write names ("France", "USA"). The names are the browser's own,
 * in the site's English.
 */
import { LOCALE } from "./locale";
import { fold } from "./text";

const NAMES = new Intl.DisplayNames([LOCALE], { type: "region", fallback: "code" });

// Names people write for countries the browser names otherwise ("United States", "United
// Kingdom", "South Korea", "Hong Kong SAR China"), folded.
const ALIASES: Readonly<Record<string, string>> = {
  usa: "US",
  us: "US",
  "u.s.": "US",
  "u.s.a.": "US",
  america: "US",
  "united states of america": "US",
  uk: "GB",
  "u.k.": "GB",
  britain: "GB",
  "great britain": "GB",
  england: "GB",
  korea: "KR",
  "republic of korea": "KR",
  "hong kong": "HK",
  prc: "CN",
  "p.r. china": "CN",
};

/** A country's name: "France" for FR; the code itself where the browser knows none. */
export function countryName(code: string): string {
  try {
    return NAMES.of(code) ?? code;
  } catch {
    return code;
  }
}

/**
 * The country a text names, among `codes` (those of the papers at hand): FR for "france",
 * US for "USA"; `null` for a text that names none of them, which is no country's name.
 */
export function countryNamed(text: string, codes: Iterable<string>): string | null {
  const key = fold(text).trim();
  if (key === "") return null;
  const alias = ALIASES[key];
  for (const code of codes) {
    if (code === alias || fold(countryName(code)) === key) return code;
  }
  return null;
}
