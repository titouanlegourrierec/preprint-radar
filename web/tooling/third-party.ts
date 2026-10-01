// Resources the built site would load from another origin, which the About page says there
// are none of: a script, stylesheet, image or frame in the HTML, a `url()` or `@import` in
// the CSS, a `fetch()`, `import()` or `.src =` in the JavaScript. Links are not loads.
const HTML_RE =
  /<(?:script|link|img|iframe|source|video|audio|embed|object)\b[^>]*?\s(?:src|href|data)\s*=\s*["']?(?:https?:)?\/\//gi;
const CSS_RE = /(?:url\(\s*["']?|@import\s+["'])(?:https?:)?\/\//gi;
const JS_RE =
  /(?:\b(?:fetch|import|importScripts|EventSource|WebSocket|Worker)\s*\(\s*|\.src\s*=\s*)["'`](?:https?:|wss?:)?\/\//gi;

/** The third-party loads of one built file (empty for files that are neither HTML, CSS nor JS). */
export function thirdPartyLoads(fileName: string, code: string): string[] {
  const pattern = fileName.endsWith(".html")
    ? HTML_RE
    : fileName.endsWith(".css")
      ? CSS_RE
      : fileName.endsWith(".js")
        ? JS_RE
        : null;
  return pattern ? [...code.matchAll(pattern)].map((match) => match[0]) : [];
}
