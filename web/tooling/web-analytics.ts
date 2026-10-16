/**
 * Cloudflare Web Analytics (UX-47): visits counted without cookies or anything stored in the
 * browser, by a script of Cloudflare's, the only thing the site loads from another origin,
 * and only when the build is given the site's token (`PREPRINT_RADAR_ANALYTICS_TOKEN`, a
 * repository variable: it is no secret, every page shows it). Without it, the site loads
 * nothing from elsewhere, as the About page then says. The script reports each page's
 * address without its query and fragment (the search, a shared folder), as its code read
 * on 2026-10-16 does.
 */

export const BEACON_URL = "https://static.cloudflareinsights.com/beacon.min.js";
/** Where the script sends what it counts. */
export const REPORT_URL = "https://cloudflareinsights.com/cdn-cgi/rum";

// A token goes into the page's HTML: letters, digits, `-` and `_` only.
const TOKEN_RE = /^[\w-]{16,64}$/;

/** The site's token, `null` when none is given; a malformed one fails the build. */
export function analyticsToken(value: string | undefined): string | null {
  const token = value?.trim() ?? "";
  if (token === "") return null;
  if (!TOKEN_RE.test(token)) {
    throw new Error("PREPRINT_RADAR_ANALYTICS_TOKEN is not a Cloudflare Web Analytics site token");
  }
  return token;
}

/**
 * The script's tag, as Cloudflare's snippet writes it (a module since 2026, which finds its
 * token by `data-cf-beacon`, and which its server allows any origin to load), for the end
 * of `index.html`.
 */
export function beaconTag(token: string): string {
  return `<script type="module" src="${BEACON_URL}" data-cf-beacon='{"token": "${token}"}'></script>`;
}
