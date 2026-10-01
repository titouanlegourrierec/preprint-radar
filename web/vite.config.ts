import { cpSync, createReadStream, existsSync, statSync } from "node:fs";
import { basename, resolve, sep } from "node:path";
import preact from "@preact/preset-vite";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

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

export default defineConfig({
  // Relative base: the site works under any GitHub Pages path (user.github.io/<repo>/).
  base: "./",
  plugins: [preact(), paperData(DATA_DIR)],
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
