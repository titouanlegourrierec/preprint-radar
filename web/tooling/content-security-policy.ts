/**
 * The Content-Security-Policy of the built site (SEC-1): its own scripts, styles, data and
 * graph worker only, and the emoji favicon's `data:` image. The site renders third-party
 * text and links (titles, abstracts, comments), which this keeps from ever running a
 * script or loading anything; `vite.config.ts` adds it to `index.html`.
 */
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
].join("; ");
