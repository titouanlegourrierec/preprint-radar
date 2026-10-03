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
import preact from "@preact/preset-vite";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";
import type { ScholarFile, StoreIndex } from "./src/types";
import { citationShardFiles } from "./tooling/citation-shards";
import { paperFiles, withScholar } from "./tooling/scholar";
import { thirdPartyLoads } from "./tooling/third-party";

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
 * the index or a `citations.json` changes (`make citations` while the server runs).
 */
function shardsOf(dataDir: string): () => Map<string, string> {
  let cached: { stamp: string; files: Map<string, string> } | null = null;
  return () => {
    const sources = existsSync(dataDir)
      ? [
          resolve(dataDir, "index.json"),
          ...readdirSync(dataDir).map((name) => resolve(dataDir, name, "citations.json")),
        ].filter((path) => existsSync(path))
      : [];
    const stamp = sources.map((path) => `${path}@${statSync(path).mtimeMs}`).join("\n");
    if (cached?.stamp !== stamp) cached = { stamp, files: citationShardFiles(jsonReader(dataDir)) };
    return cached.files;
  };
}

// A day or archive file, whose records the site gets with their DOI and published venue.
const PAPER_FILE_RE = /^\/([^/]+)\/(?:\d{4}-\d{2}-\d{2}|archive\/\d{4})\.json$/;

/**
 * Serve the repository's `data/` store at `/data` during development and copy it into the
 * build output, so the Python pipeline and the web app share a single source of truth. What
 * only the site uses is derived from it here, not stored: the citation shards, and the
 * records with what `scholar.json` knows (`tooling/scholar.ts`).
 */
function paperData(dataDir: string): Plugin {
  const shards = shardsOf(dataDir);
  const read = jsonReader(dataDir);
  const scholarOf = (category: string) => read(`${category}/scholar.json`) as ScholarFile | null;
  return {
    name: "preprint-radar:data",
    configureServer(server) {
      server.middlewares.use("/data", (req, res, next) => {
        const path = decodeURIComponent((req.url ?? "/").split("?")[0] ?? "/");
        const shard = shards().get(path.slice(1));
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
        const category = PAPER_FILE_RE.exec(path)?.[1];
        if (category !== undefined) {
          res.end(withScholar(readFileSync(file, "utf8"), scholarOf(category)));
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
        for (const [path, text] of shards()) {
          const target = resolve(output, path);
          mkdirSync(dirname(target), { recursive: true });
          writeFileSync(target, text);
        }
        const index = read("index.json") as StoreIndex | null;
        const scholars = new Map<string, ScholarFile | null>();
        for (const { category, path } of index ? paperFiles(index) : []) {
          if (!scholars.has(category)) scholars.set(category, scholarOf(category));
          const scholar = scholars.get(category) ?? null;
          const target = resolve(output, path);
          if (scholar !== null && existsSync(target)) {
            writeFileSync(target, withScholar(readFileSync(target, "utf8"), scholar));
          }
        }
      }
    },
  };
}

/** Fail the build if the site would load anything from another origin (see About, privacy). */
function noThirdPartyLoads(): Plugin {
  return {
    name: "preprint-radar:no-third-party-loads",
    apply: "build",
    // After Vite has emitted index.html.
    enforce: "post",
    generateBundle(_, bundle) {
      for (const [fileName, output] of Object.entries(bundle)) {
        const code = output.type === "chunk" ? output.code : String(output.source);
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
  plugins: [preact(), paperData(DATA_DIR), noThirdPartyLoads()],
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
        "src/download.ts",
        "src/keyboard.ts",
        "src/main.tsx",
      ],
      reporter: ["text-summary"],
      thresholds: { perFile: true, lines: 90, statements: 90, functions: 85, branches: 70 },
    },
  },
});
