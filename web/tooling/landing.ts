/**
 * Most bytes, gzipped, that the landing page may load before its data (PERF-15): its HTML,
 * script and stylesheet, 56 kB on 2026-10-15 once the graph loaded on demand (PERF-13). The
 * build fails past it: a dependency or a module the list does not need, imported eagerly.
 */
export const LANDING_BUDGET = 75_000;

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
