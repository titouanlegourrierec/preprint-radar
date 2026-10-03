import { cpSync, createReadStream, existsSync, statSync } from "node:fs";
import { basename, resolve, sep } from "node:path";
import preact from "@preact/preset-vite";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";
import { thirdPartyLoads } from "./tooling/third-party";

const DATA_DIR = resolve(import.meta.dirname, "..", "data");

/**
 * Serve the repository's `data/` store at `/data` during development and copy it into the
 * build output, so the Python pipeline and the web app share a single source of truth.
 */
function paperData(dataDir: string): Plugin {
  return {
    name: "preprint-radar:data",
    configureServer(server) {
      server.middlewares.use("/data", (req, res, next) => {
        const file = resolve(
          dataDir,
          `.${decodeURIComponent((req.url ?? "/").split("?")[0] ?? "/")}`,
        );
        if (!file.startsWith(dataDir + sep) || !existsSync(file) || !statSync(file).isFile()) {
          next();
          return;
        }
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        createReadStream(file).pipe(res);
      });
    },
    writeBundle(options) {
      if (options.dir && existsSync(dataDir)) {
        // Not the leftovers of an interrupted write, nor dotfiles (.DS_Store).
        cpSync(dataDir, resolve(options.dir, "data"), {
          recursive: true,
          filter: (source) => !basename(source).startsWith(".") && !source.endsWith(".tmp"),
        });
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
