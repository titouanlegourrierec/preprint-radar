/**
 * The version of each data file the site loads (PERF-8). GitHub Pages lets browsers keep a
 * file ten minutes: after a deploy, one could mix the fresh index with a day file, a search
 * shard or a citation shard kept from before it. The build writes the version of each file
 * into the site's `index.json`, and the site asks for `<path>?v=<version>`: a file the
 * deploy changed has a new address, one it did not is still taken from the cache. The paths
 * stay those of the store, which the feeds, saved papers (`light`) and links name.
 */

/** Hexadecimal digits of a version: the first ten of the file's SHA-256. */
const VERSION_DIGITS = 10;

/**
 * The version of each file that exists, by its path under `data/`: the start of the
 * hexadecimal SHA-256 of its bytes (`sha256`, Node's in the build), which changes when they do.
 */
export function fileVersions(
  paths: Iterable<string>,
  read: (path: string) => Uint8Array | null,
  sha256: (content: Uint8Array) => string,
): Map<string, string> {
  const versions = new Map<string, string>();
  for (const path of paths) {
    const content = read(path);
    if (content !== null) versions.set(path, sha256(content).slice(0, VERSION_DIGITS));
  }
  return versions;
}

/** The site's `index.json`: the store's, with the version of each file, by path under `data/`. */
export function withVersions(indexText: string, versions: ReadonlyMap<string, string>): string {
  const index = JSON.parse(indexText) as Record<string, unknown>;
  index.versions = Object.fromEntries([...versions].sort(([a], [b]) => a.localeCompare(b)));
  return `${JSON.stringify(index)}\n`;
}
