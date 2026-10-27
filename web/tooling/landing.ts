/**
 * Most bytes, gzipped, that the landing page may load before its data (PERF-15): its HTML,
 * script and stylesheet, 56 kB on 2026-10-15 once the graph loaded on demand (PERF-13). The
 * build fails past it: a dependency or a module the list does not need, imported eagerly.
 * 100 kB from 75 since 2026-10-27, the page at 74 (PERF-18): its first data, a day file of
 * 100 to 220 kB gzipped, weighs more, and the list's small touches need room. The world map
 * (49 kB) imported eagerly still fails it; the graph (14 kB) or Trends (7.5 kB) alone no
 * longer do.
 */
export const LANDING_BUDGET = 100_000;

// The files of the build that `index.html` loads: its script, stylesheet and module preloads.
const ASSET_RE = /(?:src|href)="\.\/(assets\/[^"]+\.(?:js|css))"/g;

/** The assets `index.html` loads, in order, once each. */
export function landingAssets(html: string): string[] {
  return [...new Set([...html.matchAll(ASSET_RE)].map((match) => match[1] ?? ""))];
}

/**
 * The landing page's files with their sizes, gzipped by `gzipSize` as GitHub Pages serves
 * them (`vite.config.ts` passes zlib's), and the line the build prints.
 */
export function landingReport(
  files: ReadonlyMap<string, string>,
  gzipSize: (text: string) => number,
): { bytes: number; line: string } {
  const sizes = [...files].map(([name, text]) => ({ name, bytes: gzipSize(text) }));
  const bytes = sizes.reduce((sum, { bytes }) => sum + bytes, 0);
  const kilobytes = (count: number) => `${(count / 1000).toFixed(1)} kB`;
  const parts = sizes.map(({ name, bytes }) => `${name} ${kilobytes(bytes)}`).join(", ");
  return {
    bytes,
    line: `Landing page: ${kilobytes(bytes)} gzipped of ${kilobytes(LANDING_BUDGET)} (${parts})`,
  };
}
