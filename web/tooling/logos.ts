/**
 * The logos of major institutions (PROD-23), chosen one by one by hand (`make logo`): each
 * file of `public/logos/` is listed in `logos.json` with where it was taken from and its
 * license. The site serves them from its own origin, where opening one directly would run
 * any script it holds, so the build refuses a file that could run code or load anything.
 */

/** A logo of `logos.json`. */
export interface LogoEntry {
  /** Its file under `public/logos/`, named after the institution and its content's hash. */
  file: string;
  /** The file's own page: on Commons, or the Wikipedia that holds it, or the institution's. */
  source: string;
  /** Its license there ("Public domain, trademarked"), or why the site may show it. */
  license: string;
}

/** `logos.json`: the logos by institution, named as the site names it (`institutions`). */
export interface LogosManifest {
  logos: Record<string, LogoEntry>;
}

/** Where the logos are served, under the site's base, as under `public/`. */
export const LOGO_DIR = "logos";

// A logo is drawn at most 44 px high: a larger file is not a logo.
const MAX_BYTES = 100_000;
// A raster below this blurs on a high-density screen even at the card's 16 px.
const MIN_PIXELS = 64;
const FILE_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*-([0-9a-f]{8})\.(svg|png)$/;
const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

// What an SVG must not hold: code, entities, elements that load, link or animate.
const SVG_REFUSED: [RegExp, string][] = [
  [/<script\b/i, "a script"],
  [/<foreignObject\b/i, "a foreignObject"],
  [/<!(?:DOCTYPE|ENTITY)\b/i, "a DOCTYPE or an entity"],
  [/<(?:a|image|feImage|iframe|embed|object|audio|video)\b/i, "an element that loads or links"],
  [/<(?:animate|set)\w*\b/i, "an animation"],
  [/\son[a-z]+\s*=/i, "an event handler"],
  [/javascript:/i, "a javascript: URL"],
  [/@import\b/i, "an @import"],
];
const HREF_RE = /\s(?:xlink:)?href\s*=\s*(["'])(.*?)\1/gi;
const CSS_URL_RE = /url\(\s*(["']?)(.*?)\1\s*\)/gi;
const ROOT_RE = /<svg\b[^>]*>/i;
const VIEW_BOX_RE = /\sviewBox\s*=\s*(["'])(.*?)\1/i;

/** Why an SVG cannot be served as a logo; empty when it can. */
export function svgProblems(text: string): string[] {
  const problems: string[] = [];
  const root = ROOT_RE.exec(text)?.[0];
  if (root === undefined || !text.trimEnd().endsWith("</svg>")) return ["not an SVG"];
  if (!VIEW_BOX_RE.test(root)) problems.push("no viewBox on its root, so it cannot scale");
  for (const [pattern, what] of SVG_REFUSED) {
    if (pattern.test(text)) problems.push(`holds ${what}`);
  }
  for (const [, , target] of [...text.matchAll(HREF_RE), ...text.matchAll(CSS_URL_RE)]) {
    if (!target?.startsWith("#")) problems.push(`refers outside itself (${target})`);
  }
  return problems;
}

/** A PNG's width and height, from its header; `null` when it is not a PNG. */
export function pngSize(bytes: Uint8Array): { width: number; height: number } | null {
  if (bytes.length < 24 || PNG_SIGNATURE.some((byte, i) => bytes[i] !== byte)) return null;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return { width: view.getUint32(16), height: view.getUint32(20) };
}

/** Why a file cannot be served as a logo, by its extension (`svg`, `png`); empty when it can. */
export function contentProblems(extension: string, bytes: Uint8Array): string[] {
  const problems =
    bytes.length > MAX_BYTES ? [`${bytes.length} bytes, past the ${MAX_BYTES} of a logo`] : [];
  if (extension === "svg") return [...problems, ...svgProblems(new TextDecoder().decode(bytes))];
  const size = pngSize(bytes);
  if (size === null) return [...problems, "not a PNG"];
  if (Math.min(size.width, size.height) < MIN_PIXELS) {
    problems.push(`${size.width}×${size.height} px, below ${MIN_PIXELS} px a side`);
  }
  return problems;
}

/**
 * Why the logos of `logos.json` cannot be served, each problem naming its institution or
 * file: a file missing, unsafe or not named after its content's hash (`hash`, hexadecimal),
 * an entry without its source or license, a file of `public/logos/` (`files`) not listed.
 */
export function logoProblems(
  manifest: LogosManifest,
  files: readonly string[],
  read: (file: string) => Uint8Array | null,
  hash: (bytes: Uint8Array) => string,
): string[] {
  const problems: string[] = [];
  const listed = new Set<string>();
  for (const [name, entry] of Object.entries(manifest.logos)) {
    listed.add(entry.file);
    const say = (problem: string) => problems.push(`${name}: ${problem}`);
    if (name.trim() !== name || name === "") say("a name with spaces around it");
    if (!entry.source?.startsWith("https://")) say("no https source");
    if (!entry.license?.trim()) say("no license");
    const match = FILE_RE.exec(entry.file ?? "");
    if (match === null) {
      say(`${entry.file} is not named <name>-<hash>.svg or .png`);
      continue;
    }
    const bytes = read(entry.file);
    if (bytes === null) {
      say(`${entry.file} is missing`);
      continue;
    }
    if (!hash(bytes).startsWith(match[1] ?? "")) say(`${entry.file} is not its content's hash`);
    for (const problem of contentProblems(match[2] ?? "", bytes)) say(`${entry.file}: ${problem}`);
  }
  for (const file of files) {
    if (!listed.has(file)) problems.push(`${file} is not in logos.json`);
  }
  return problems;
}

/** The file name of a logo: the institution's name as a slug, then its content's hash. */
export function logoFileName(name: string, extension: string, hash: string): string {
  const slug = name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `${slug}-${hash.slice(0, 8)}.${extension}`;
}

// The DOCTYPE editors write by default: it names SVG 1.1's DTD and declares nothing.
const BARE_DOCTYPE_RE = /<!DOCTYPE\s+svg\s+PUBLIC\s+"[^"[\]]*"\s+"[^"[\]]*"\s*>\s*/i;

/**
 * An SVG as an editor saved it, made fit to check: the DOCTYPE Illustrator and Inkscape
 * write by default goes, and a root sized in pixels or points without a viewBox gets one
 * from its size, in CSS pixels, its drawing's units, so that it scales. A DOCTYPE that
 * declares anything stays, for `svgProblems` to refuse.
 */
export function tidySvg(text: string): string {
  const tidy = text.replace(BARE_DOCTYPE_RE, "");
  const root = ROOT_RE.exec(tidy)?.[0];
  if (root === undefined || VIEW_BOX_RE.test(root)) return tidy;
  const size = (name: string) => {
    const match = new RegExp(`\\s${name}\\s*=\\s*["']\\s*([\\d.]+)\\s*(px|pt)?\\s*["']`, "i").exec(
      root,
    );
    const pixels = match?.[2]?.toLowerCase() === "pt" ? 4 / 3 : 1;
    return Number(match?.[1]) * pixels;
  };
  const [width, height] = [size("width"), size("height")];
  if (!(width > 0 && height > 0)) return tidy;
  const viewBox = `0 0 ${Number(width.toFixed(3))} ${Number(height.toFixed(3))}`;
  return tidy.replace(root, root.replace(/^<svg\b/i, `<svg viewBox="${viewBox}"`));
}

/**
 * An SVG cropped to `viewBox` ("x y width height"), as the Adobe mark is cut out of its
 * wordmark; its root's width and height go, which would keep the uncropped proportions.
 */
export function cropSvg(text: string, viewBox: string): string {
  const numbers = viewBox
    .trim()
    .split(/[\s,]+/)
    .map(Number);
  const [, , width = 0, height = 0] = numbers;
  if (numbers.length !== 4 || numbers.some(Number.isNaN) || width <= 0 || height <= 0) {
    throw new Error(`"${viewBox}" is not a viewBox: x y width height, the last two above 0`);
  }
  const root = ROOT_RE.exec(text)?.[0];
  if (root === undefined) throw new Error("not an SVG");
  const bare = root
    .replace(VIEW_BOX_RE, "")
    .replace(/\s(?:width|height)\s*=\s*(["']).*?\1/gi, "")
    .replace(/^<svg\b/i, `<svg viewBox="${numbers.join(" ")}"`);
  return text.replace(root, bare);
}

// A file's page on Commons or on a Wikipedia, in any language ("Datei:", "Dosiye:"), or an
// article's media viewer ("#/media/File:…").
const WIKI_PAGE_RE =
  /^https:\/\/([a-z-]+\.wikipedia\.org|commons\.wikimedia\.org)\/wiki\/([^?#]+)(?:\?[^#]*)?(?:#\/media\/([^?#]+))?$/;

/**
 * The API queries for the file a wiki page shows: its page on Commons or on a Wikipedia in
 * any language, or an article's media viewer, its namespace's local name taken as `File:`.
 * Commons first, which holds nearly every file the Wikipedias show (and answers when their
 * API refuses a burst of requests), then the page's own wiki, for a file of its own. Empty
 * for another page, or an article without a file shown.
 */
export function wikiFileQueries(page: string): string[] {
  const [, host, path, media] = WIKI_PAGE_RE.exec(page) ?? [];
  const title = decodeURIComponent(media ?? path ?? "");
  const colon = title.indexOf(":");
  if (host === undefined || colon < 0) return [];
  const query = new URLSearchParams({
    action: "query",
    format: "json",
    prop: "imageinfo",
    iiprop: "url|extmetadata",
    titles: `File:${title.slice(colon + 1)}`,
  });
  return [...new Set(["commons.wikimedia.org", host])].map(
    (wiki) => `https://${wiki}/w/api.php?${query}`,
  );
}

/** A file a wiki's API describes. */
export interface WikiFile {
  /** The original file, without the tracking parameters the API appends. */
  url: string;
  /** Its own page: on Commons for a shared file, else on the wiki that holds it. */
  page: string;
  /** Its license ("Public domain, trademarked"). */
  license: string;
  /** Whether the wiki shows it under fair use only, which covers its articles, not this site. */
  nonFree: boolean;
}

/** The file of a wiki API's answer about one; `null` without a file. */
export function wikiFile(answer: unknown): WikiFile | null {
  interface Answer {
    query?: {
      pages?: Record<
        string,
        {
          imageinfo?: {
            url?: string;
            descriptionurl?: string;
            extmetadata?: Record<string, { value?: string } | undefined>;
          }[];
        }
      >;
    };
  }
  const page = Object.values((answer as Answer).query?.pages ?? {})[0];
  const info = page?.imageinfo?.[0];
  if (info?.url === undefined) return null;
  const metadata = info.extmetadata ?? {};
  const license = metadata.LicenseShortName?.value ?? "unknown license";
  const trademarked = metadata.Restrictions?.value?.split("|").includes("trademarked");
  const url = info.url.split("?")[0] ?? info.url;
  return {
    url,
    page: info.descriptionurl ?? url,
    license: trademarked ? `${license}, trademarked` : license,
    nonFree: metadata.NonFree?.value === "true" || /non-free|fair use/i.test(license),
  };
}

/** Whether bytes are a JPEG, by its signature. */
export function isJpeg(bytes: Uint8Array): boolean {
  return bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
}

/** The site's path of each logo by institution: `logos/<file>`. */
export function logoPaths(manifest: LogosManifest): Record<string, string> {
  return Object.fromEntries(
    Object.entries(manifest.logos).map(([name, { file }]) => [name, `${LOGO_DIR}/${file}`]),
  );
}

/** The site's `index.json` with the logos' paths by institution (PROD-23). */
export function withLogos(indexText: string, logos: Record<string, string>): string {
  if (Object.keys(logos).length === 0) return indexText;
  const index = JSON.parse(indexText) as Record<string, unknown>;
  index.logos = logos;
  return `${JSON.stringify(index)}\n`;
}
