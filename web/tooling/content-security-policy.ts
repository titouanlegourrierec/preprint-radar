import { BEACON_URL, REPORT_URL } from "./web-analytics";

/**
 * The Content-Security-Policy of the built site (SEC-1): its own scripts, styles, data,
 * images (the logo's icons, UX-48) and graph worker only. The site renders third-party
 * text and links (titles, abstracts, comments), which this keeps from ever running a
 * script or loading anything; `vite.config.ts` adds it to `index.html`. With Cloudflare
 * Web Analytics (UX-47), its script and the address it reports to, those two only.
 */
export function contentSecurityPolicy(analytics: boolean): string {
  const counted = (sources: string, url: string) => (analytics ? `${sources} ${url}` : sources);
  return [
    "default-src 'self'",
    counted("script-src 'self'", BEACON_URL),
    "style-src 'self'",
    "img-src 'self'",
    counted("connect-src 'self'", REPORT_URL),
    "object-src 'none'",
    "base-uri 'none'",
  ].join("; ");
}

/** The policy of a site without analytics, which the smoke test's build is. */
export const CONTENT_SECURITY_POLICY = contentSecurityPolicy(false);
