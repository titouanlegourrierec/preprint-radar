/**
 * Add or replace an institution's logo by hand (PROD-23, `make logo`): the file a wiki page
 * shows (its page on Commons or on a Wikipedia, or an article's media viewer), or any https
 * file given its license. An SVG is tidied (`tidySvg`), cropped to `--view-box` and drawn as
 * a PNG `--png` pixels high if asked; a JPEG becomes a PNG (128 pixels high by default), the
 * site serving SVG and PNG only. Then it is checked as the build checks it, written to
 * `public/logos/` under its content's hash and listed in `logos.json` with the file's own
 * page. Look at it next: `make logos-review`.
 *
 *   node tooling/add-logo.ts --name "Stanford University" --url <file page>
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import {
  contentProblems,
  cropSvg,
  isJpeg,
  type LogosManifest,
  logoFileName,
  pngSize,
  svgProblems,
  tidySvg,
  type WikiFile,
  wikiFile,
  wikiFileQueries,
} from "./logos.ts";

const WEB = resolve(import.meta.dirname, "..");
const MANIFEST = resolve(WEB, "logos.json");
const LOGOS = resolve(WEB, "public", "logos");
const DATA = resolve(WEB, "..", "data");
// Wikimedia asks every client to name itself and how to reach its maintainers.
const USER_AGENT = "preprint-radar-logos (https://github.com/titouanlegourrierec/preprint-radar)";

// Wikimedia refuses a burst of requests (429, 503), or drops the connection, for up to a
// minute: asked again after its Retry-After, two minutes at most, else these.
const RETRY_SECONDS = [5, 20, 60];
const MAX_WAIT_SECONDS = 120;
const TIMEOUT_MS = 30_000;
// Three times the largest size the site shows a logo.
const PNG_HEIGHT = 128;

async function download(url: string): Promise<Response> {
  let failure = "";
  let wait = 0;
  for (const fallback of [...RETRY_SECONDS, 0]) {
    await new Promise((done) => setTimeout(done, wait * 1000));
    const response = await fetch(url, {
      headers: { "User-Agent": USER_AGENT },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    }).catch((error: unknown) => error);
    wait = fallback;
    if (!(response instanceof Response)) {
      failure = String(response);
      continue;
    }
    if (response.ok) return response;
    if (response.status !== 429 && response.status !== 503) {
      throw new Error(`${url} answered ${response.status}`);
    }
    failure = `answered ${response.status}`;
    wait = Math.min(Number(response.headers.get("retry-after")) || fallback, MAX_WAIT_SECONDS);
  }
  throw new Error(`${url} still fails after ${RETRY_SECONDS.length} retries (${failure})`);
}

/**
 * A file drawn as a PNG `height` pixels high: an SVG too detailed to serve as one
 * (Tsinghua's seal, 327 kB of paths) by librsvg's `rsvg-convert`, a JPEG by ImageMagick,
 * never enlarged, without its metadata.
 */
function toPng(bytes: Uint8Array, kind: "svg" | "jpeg", height: number): Uint8Array {
  if (!Number.isInteger(height) || height < 64) throw new Error("--png takes 64 px or more");
  const [command, args, install] =
    kind === "svg"
      ? [
          "rsvg-convert",
          ["--format", "png", "--height", `${height}`, "--keep-aspect-ratio"],
          "librsvg",
        ]
      : ["magick", ["-", "-strip", "-resize", `x${height}>`, "png:-"], "imagemagick"];
  const result = spawnSync(command, args, { input: bytes, maxBuffer: 16_000_000 });
  if (result.error !== undefined || result.status !== 0) {
    const reason = result.error?.message ?? result.stderr.toString();
    throw new Error(`${command} failed (brew install ${install}): ${reason}`);
  }
  return new Uint8Array(result.stdout);
}

/** How many stored papers name each institution, from the day files and the archive. */
function institutionCounts(): Map<string, number> {
  const counts = new Map<string, number>();
  if (!existsSync(DATA)) return counts;
  const files = readdirSync(DATA, { recursive: true, encoding: "utf8" }).filter((path) =>
    /(?:^|\/)(?:\d{4}-\d{2}-\d{2}|archive\/\d{4})\.json$/.test(path),
  );
  for (const path of files) {
    const { papers } = JSON.parse(readFileSync(resolve(DATA, path), "utf8")) as {
      papers: { institutions?: (string | null)[] | null }[];
    };
    for (const paper of papers) {
      for (const name of new Set(paper.institutions ?? [])) {
        if (name !== null) counts.set(name, (counts.get(name) ?? 0) + 1);
      }
    }
  }
  return counts;
}

async function main(): Promise<void> {
  const { values } = parseArgs({
    options: {
      name: { type: "string" },
      url: { type: "string" },
      license: { type: "string" },
      "view-box": { type: "string" },
      png: { type: "string" },
    },
  });
  const name = values.name?.trim();
  const url = values.url;
  if (!name || !url) {
    throw new Error('usage: --name "<institution as the site names it>" --url <file or page>');
  }

  const queries = wikiFileQueries(url);
  let file = url;
  let source = url;
  let license = values.license;
  if (queries.length > 0) {
    let found: WikiFile | null = null;
    for (const query of queries) {
      if (found !== null) break;
      found = wikiFile(await (await download(query)).json());
    }
    if (found === null) throw new Error(`no file at ${url}`);
    if (found.nonFree && license === undefined) {
      throw new Error(
        `${found.page} is non-free (${found.license}): fair use covers the wiki's articles, ` +
          "not this site; --license keeps it anyway",
      );
    }
    file = found.url;
    source = found.page;
    license ??= found.license;
  }
  if (!license) throw new Error("a file outside the wikis needs its --license");

  let bytes: Uint8Array = new Uint8Array(await (await download(file)).arrayBuffer());
  const viewBox = values["view-box"];
  const height = values.png === undefined ? undefined : Number(values.png);
  let extension = "png";
  if (pngSize(bytes) !== null) {
    if (viewBox !== undefined || height !== undefined) {
      throw new Error("a PNG is kept as it is: no --view-box nor --png");
    }
  } else if (isJpeg(bytes)) {
    if (viewBox !== undefined) throw new Error("--view-box crops an SVG only");
    bytes = toPng(bytes, "jpeg", height ?? PNG_HEIGHT);
  } else {
    const text = tidySvg(new TextDecoder().decode(bytes));
    const svg = viewBox === undefined ? text : cropSvg(text, viewBox);
    bytes = new TextEncoder().encode(svg);
    extension = "svg";
    if (height !== undefined) {
      const unsafe = svgProblems(svg).filter((problem) => !problem.startsWith("no viewBox"));
      if (unsafe.length > 0) throw new Error(`${file}: ${unsafe.join("; ")}`);
      bytes = toPng(bytes, "svg", height);
      extension = "png";
    }
  }
  const problems = contentProblems(extension, bytes);
  if (problems.length > 0) throw new Error(`${file}: ${problems.join("; ")}`);

  const manifest: LogosManifest = existsSync(MANIFEST)
    ? (JSON.parse(readFileSync(MANIFEST, "utf8")) as LogosManifest)
    : { logos: {} };
  const target = logoFileName(name, extension, createHash("sha256").update(bytes).digest("hex"));
  const previous = manifest.logos[name]?.file;
  mkdirSync(LOGOS, { recursive: true });
  writeFileSync(resolve(LOGOS, target), bytes);
  // The file it replaces, unless another institution shares it.
  const shared = Object.entries(manifest.logos).some(
    ([other, entry]) => other !== name && entry.file === previous,
  );
  if (previous !== undefined && previous !== target && !shared) {
    rmSync(resolve(LOGOS, previous), { force: true });
  }
  manifest.logos[name] = { file: target, source, license };
  const sorted = Object.fromEntries(
    Object.entries(manifest.logos).sort(([a], [b]) => a.localeCompare(b, "en")),
  );
  writeFileSync(MANIFEST, `${JSON.stringify({ logos: sorted }, null, 2)}\n`);
  console.log(`${name}: public/logos/${target} (${bytes.length} bytes, ${license})`);

  const counts = institutionCounts();
  const papers = counts.get(name) ?? 0;
  if (papers > 0) {
    console.log(`${papers} stored papers name it.`);
    return;
  }
  const words = name.toLowerCase().split(/\W+/).filter(Boolean);
  const close = [...counts]
    .filter(([other]) => words.some((word) => other.toLowerCase().includes(word)))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  console.warn(`No stored paper names "${name}", so the site never shows this logo.`);
  for (const [other, count] of close) console.warn(`  did you mean "${other}" (${count} papers)?`);
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
