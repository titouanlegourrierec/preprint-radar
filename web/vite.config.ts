import { createHash } from "node:crypto";
import {
  cpSync,
  createReadStream,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, resolve, sep } from "node:path";
import { gzipSync } from "node:zlib";
import preact from "@preact/preset-vite";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";
import type { CodeFile, Cohort, CohortsFile, ScholarFile, StoreIndex } from "./src/types";
import type { CountriesFile } from "./src/world";
import { citationShardFiles } from "./tooling/citation-shards";
import { withCohorts } from "./tooling/cohorts";
import { contentSecurityPolicy as policy } from "./tooling/content-security-policy";
import { fileVersions, withVersions } from "./tooling/data-versions";
import { feedFiles } from "./tooling/feeds";
import { LANDING_BUDGET, landingAssets, landingReport } from "./tooling/landing";
import { paperFiles, withSiteFields } from "./tooling/scholar";
import { searchShardFiles } from "./tooling/search-shards";
import { shareImageTags } from "./tooling/share-card";
import { thirdPartyLoads } from "./tooling/third-party";
import { analyticsToken, beaconTag } from "./tooling/web-analytics";

// The repository's store; the smoke test (e2e/) builds the site over a small one instead.
const DATA_DIR = resolve(
  import.meta.dirname,
  process.env.PREPRINT_RADAR_DATA_DIR ?? resolve(import.meta.dirname, "..", "data"),
);

/** Reads a JSON file of the store by its path under `data/`; `null` when there is none. */
function jsonReader(dataDir: string): (path: string) => unknown {
  return (path) => {
    const file = resolve(dataDir, path);
    return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as unknown) : null;
  };
}

/**
 * The citation shards of the store (`src/citations.ts`), derived again in development when
 * the index, a `citations.json` or its gains change (`make citations` while the server runs).
 */
function shardsOf(dataDir: string): () => Map<string, string> {
  let cached: { stamp: string; files: Map<string, string> } | null = null;
  return () => {
    const sources = existsSync(dataDir)
      ? [
          resolve(dataDir, "index.json"),
          ...readdirSync(dataDir).flatMap((name) => [
            resolve(dataDir, name, "citations.json"),
            resolve(dataDir, name, "citation-gains.json"),
          ]),
        ].filter((path) => existsSync(path))
      : [];
    const stamp = sources.map((path) => `${path}@${statSync(path).mtimeMs}`).join("\n");
    if (cached?.stamp !== stamp) cached = { stamp, files: citationShardFiles(jsonReader(dataDir)) };
    return cached.files;
  };
}

/**
 * The search shards of the store (`src/search-shards.ts`), derived again in development when
 * the index (a new day, or day files written again), a `scholar.json` or a `code.json` changes.
 */
function searchShardsOf(dataDir: string): () => Map<string, string> {
  let cached: { stamp: string; files: Map<string, string> } | null = null;
  return () => {
    const sources = existsSync(dataDir)
      ? [
          resolve(dataDir, "index.json"),
          ...readdirSync(dataDir).flatMap((name) => [
            resolve(dataDir, name, "scholar.json"),
            resolve(dataDir, name, "code.json"),
          ]),
        ].filter((path) => existsSync(path))
      : [];
    const stamp = sources.map((path) => `${path}@${statSync(path).mtimeMs}`).join("\n");
    if (cached?.stamp !== stamp) cached = { stamp, files: searchShardFiles(jsonReader(dataDir)) };
    return cached.files;
  };
}

// The site's address, which the feeds' links need; the deploy workflow sets it.
const SITE_URL = process.env.PREPRINT_RADAR_SITE_URL || null;
/** Cloudflare Web Analytics' site token (UX-47): visits are counted only when it is given. */
const ANALYTICS_TOKEN = analyticsToken(process.env.PREPRINT_RADAR_ANALYTICS_TOKEN);

/**
 * The Atom feeds of the store (`tooling/feeds.ts`), derived again in development when the
 * index changes (a new day) or `scholar.json` does.
 */
function feedsOf(dataDir: string): () => Map<string, string> {
  let cached: { stamp: string; files: Map<string, string> } | null = null;
  return () => {
    const sources = existsSync(dataDir)
      ? [
          resolve(dataDir, "index.json"),
          ...readdirSync(dataDir).map((name) => resolve(dataDir, name, "scholar.json")),
        ].filter((path) => existsSync(path))
      : [];
    const stamp = sources.map((path) => `${path}@${statSync(path).mtimeMs}`).join("\n");
    if (cached?.stamp !== stamp)
      cached = { stamp, files: feedFiles(jsonReader(dataDir), SITE_URL) };
    return cached.files;
  };
}

// A day or archive file, or the most cited papers of the last 12 months, whose records the
// site gets with their DOI, published venue and the stars of their code.
const PAPER_FILE_RE = /^\/([^/]+)\/(?:\d{4}-\d{2}-\d{2}|archive\/\d{4}|top-recent)\.json$/;

/**
 * Serve the repository's `data/` store at `/data` during development and copy it into the
 * build output, so the Python pipeline and the web app share a single source of truth. What
 * only the site uses is derived from it here, not stored: the citation shards, the search
 * shards, the records with what `scholar.json` and `code.json` know (`tooling/scholar.ts`,
 * `tooling/code.ts`), the Atom feeds, at `/feeds`, and the version of each file in the
 * index (`tooling/data-versions.ts`, the build only).
 */
function paperData(dataDir: string): Plugin {
  const shards = shardsOf(dataDir);
  const searchShards = searchShardsOf(dataDir);
  const feeds = feedsOf(dataDir);
  const read = jsonReader(dataDir);
  const scholarOf = (category: string) => read(`${category}/scholar.json`) as ScholarFile | null;
  const codeOf = (category: string) => read(`${category}/code.json`) as CodeFile | null;
  const countriesOf = (category: string) =>
    read(`${category}/countries.json`) as CountriesFile | null;
  // Each category's cohorts, for the site's index: the badges' "Top 1% of 2017".
  const cohortsOf = (index: StoreIndex | null) => {
    const cohorts: Record<string, Record<string, Cohort>> = {};
    for (const category of Object.keys(index?.categories ?? {})) {
      const file = read(`${category}/cohorts.json`) as CohortsFile | null;
      if (file !== null) cohorts[category] = file.years;
    }
    return cohorts;
  };
  return {
    name: "preprint-radar:data",
    configureServer(server) {
      server.middlewares.use("/feeds", (req, res, next) => {
        const path = decodeURIComponent((req.url ?? "/").split("?")[0] ?? "/");
        const feed = feeds().get(`feeds${path}`);
        if (feed === undefined) {
          next();
          return;
        }
        res.setHeader("Content-Type", "application/atom+xml; charset=utf-8");
        res.end(feed);
      });
      server.middlewares.use("/data", (req, res, next) => {
        const path = decodeURIComponent((req.url ?? "/").split("?")[0] ?? "/");
        const shard = shards().get(path.slice(1)) ?? searchShards().get(path.slice(1));
        if (shard !== undefined) {
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.end(shard);
          return;
        }
        const file = resolve(dataDir, `.${path}`);
        if (!file.startsWith(dataDir + sep) || !existsSync(file) || !statSync(file).isFile()) {
          next();
          return;
        }
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        if (path === "/index.json") {
          const text = readFileSync(file, "utf8");
          res.end(withCohorts(text, cohortsOf(JSON.parse(text) as StoreIndex)));
          return;
        }
        const category = PAPER_FILE_RE.exec(path)?.[1];
        if (category !== undefined) {
          const text = readFileSync(file, "utf8");
          res.end(
            withSiteFields(text, scholarOf(category), codeOf(category), countriesOf(category)),
          );
          return;
        }
        createReadStream(file).pipe(res);
      });
    },
    writeBundle(options) {
      if (options.dir && existsSync(dataDir)) {
        const output = resolve(options.dir, "data");
        // Not the leftovers of an interrupted write, nor dotfiles (.DS_Store).
        cpSync(dataDir, output, {
          recursive: true,
          filter: (source) => !basename(source).startsWith(".") && !source.endsWith(".tmp"),
        });
        for (const [path, text] of [...shards(), ...searchShards()]) {
          const target = resolve(output, path);
          mkdirSync(dirname(target), { recursive: true });
          writeFileSync(target, text);
        }
        for (const [path, text] of feeds()) {
          const target = resolve(options.dir, path);
          mkdirSync(dirname(target), { recursive: true });
          writeFileSync(target, text);
        }
        const index = read("index.json") as StoreIndex | null;
        const merged = new Map<
          string,
          [ScholarFile | null, CodeFile | null, CountriesFile | null]
        >();
        for (const { category, path } of index ? paperFiles(index) : []) {
          if (!merged.has(category)) {
            merged.set(category, [scholarOf(category), codeOf(category), countriesOf(category)]);
          }
          const [scholar, code, countries] = merged.get(category) ?? [null, null, null];
          const target = resolve(output, path);
          if ((scholar !== null || code !== null || countries !== null) && existsSync(target)) {
            writeFileSync(
              target,
              withSiteFields(readFileSync(target, "utf8"), scholar, code, countries),
            );
          }
        }
        // Last, the version of each file the site loads, as written (PERF-8).
        const loadable = [
          ...(index ? paperFiles(index).map(({ path }) => path) : []),
          ...(index
            ? Object.keys(index.categories).flatMap((category) =>
                ["countries.json", "trends.json", "topics.json"].map(
                  (name) => `${category}/${name}`,
                ),
              )
            : []),
          ...shards().keys(),
          ...searchShards().keys(),
        ];
        const versions = fileVersions(
          loadable,
          (path) => {
            const target = resolve(output, path);
            return existsSync(target) ? readFileSync(target) : null;
          },
          (content) => createHash("sha256").update(content).digest("hex"),
        );
        const indexFile = resolve(output, "index.json");
        if (existsSync(indexFile)) {
          const text = withVersions(readFileSync(indexFile, "utf8"), versions);
          writeFileSync(indexFile, withCohorts(text, cohortsOf(index)));
        }
      }
    },
  };
}

/**
 * The Content-Security-Policy as a meta (GitHub Pages sends no headers), right after the
 * charset, since it applies to what follows only, and with a token, Cloudflare Web
 * Analytics' script before the body's end, as its snippet goes (UX-47). The development
 * server goes without either, its module reloading being inline.
 */
function contentSecurityPolicy(): Plugin {
  const charset = '<meta charset="UTF-8" />';
  return {
    name: "preprint-radar:content-security-policy",
    apply: "build",
    transformIndexHtml(html) {
      if (!html.includes(charset)) throw new Error(`index.html has no ${charset} to follow`);
      const meta = `<meta http-equiv="Content-Security-Policy" content="${policy(ANALYTICS_TOKEN !== null)}" />`;
      const page = html.replace(charset, `${charset}\n    ${meta}`);
      if (ANALYTICS_TOKEN === null) return page;
      if (!page.includes("</body>")) throw new Error("index.html has no </body> to end");
      return page.replace("</body>", `  ${beaconTag(ANALYTICS_TOKEN)}\n  </body>`);
    },
  };
}

/** The image of the card a shared link shows, after the card's tags (UX-49). */
function shareCard(): Plugin {
  const anchor = '<meta name="twitter:card" content="summary_large_image" />';
  return {
    name: "preprint-radar:share-card",
    apply: "build",
    transformIndexHtml(html) {
      if (!html.includes(anchor)) throw new Error(`index.html has no ${anchor} to follow`);
      const tags = shareImageTags(SITE_URL);
      return html.replace(anchor, [anchor, ...tags].join("\n    "));
    },
  };
}

/** Print what the landing page loads, gzipped, and fail the build past its budget (PERF-15). */
function landingBudget(): Plugin {
  return {
    name: "preprint-radar:landing-budget",
    apply: "build",
    // After Vite has emitted index.html.
    enforce: "post",
    generateBundle(_, bundle) {
      const text = (name: string): string | null => {
        const output = bundle[name];
        if (output === undefined) return null;
        return output.type === "chunk" ? output.code : String(output.source);
      };
      const html = text("index.html");
      if (html === null) return;
      const files = new Map([["index.html", html]]);
      for (const asset of landingAssets(html)) files.set(asset, text(asset) ?? "");
      const { bytes, line } = landingReport(files, (code) => gzipSync(code, { level: 9 }).length);
      this.info(line);
      if (bytes > LANDING_BUDGET) this.error(`${line}: past the budget`);
    },
  };
}

/**
 * Fail the build if the site would load anything from another origin (see About, privacy),
 * but the analytics script given a token, which the policy allows alone (UX-47).
 */
function noThirdPartyLoads(): Plugin {
  const allowed = ANALYTICS_TOKEN === null ? null : beaconTag(ANALYTICS_TOKEN);
  return {
    name: "preprint-radar:no-third-party-loads",
    apply: "build",
    // After Vite has emitted index.html.
    enforce: "post",
    generateBundle(_, bundle) {
      for (const [fileName, output] of Object.entries(bundle)) {
        const emitted = output.type === "chunk" ? output.code : String(output.source);
        const code =
          allowed !== null && fileName === "index.html" ? emitted.replace(allowed, "") : emitted;
        const found = thirdPartyLoads(fileName, code);
        if (found.length > 0) {
          this.error(`${fileName} loads from another origin: ${found.join(", ")}`);
        }
      }
    },
  };
}

export default defineConfig({
  // Relative base: the site works under any GitHub Pages path (user.github.io/<repo>/).
  base: "./",
  plugins: [
    preact(),
    paperData(DATA_DIR),
    contentSecurityPolicy(),
    shareCard(),
    noThirdPartyLoads(),
    landingBudget(),
  ],
  // The graph layout runs in a module worker (graph-worker.ts), split like the app.
  worker: { format: "es" },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    // tests/styles.test.ts reads the stylesheet's text; other CSS stays empty in tests.
    css: { include: [/styles\.css/] },
    // `npm test` measures the pure modules, every one above these floors. Components,
    // hooks and what needs a DOM (canvas, downloads, keys) run in the browser only.
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: [
        "src/hooks/**",
        "src/graph-renderer.ts",
        "src/graph-worker.ts",
        "src/download.ts",
        "src/card-exit.ts",
        "src/keyboard.ts",
        "src/main.tsx",
      ],
      reporter: ["text-summary"],
      thresholds: { perFile: true, lines: 90, statements: 90, functions: 85, branches: 70 },
    },
  },
});
