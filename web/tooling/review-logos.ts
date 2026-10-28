/**
 * A sheet of every logo of `logos.json` as the site draws it (PROD-23, `make logos-review`):
 * on its white tile at the card's size and larger, on the light and the dark theme, beside
 * the bare file, with its source and license. One self-contained page, its images inline.
 *
 *   node tooling/review-logos.ts <out.html>
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { LogosManifest } from "./logos.ts";

const WEB = resolve(import.meta.dirname, "..");
// The pixel sizes of the tile: a card's affiliation, a ranking's row, a close look.
const SIZES = [16, 22, 44];
// The backgrounds of styles.css's themes, which the tile must stand out from.
const THEMES = [
  ["light", "#ffffff", "#1f2328"],
  ["dark", "#0f1219", "#e6e8ee"],
] as const;

const html = (text: string) =>
  text.replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c,
  );

const out = process.argv[2];
if (out === undefined) {
  console.error("usage: node tooling/review-logos.ts <out.html>");
  process.exit(2);
}
const manifest = JSON.parse(readFileSync(resolve(WEB, "logos.json"), "utf8")) as LogosManifest;
const rows = Object.entries(manifest.logos).map(([name, { file, source, license }]) => {
  const type = file.endsWith(".svg") ? "image/svg+xml" : "image/png";
  const data = readFileSync(resolve(WEB, "public", "logos", file)).toString("base64");
  const src = `data:${type};base64,${data}`;
  const tiles = THEMES.map(
    ([theme, background, text]) =>
      `<td style="background:${background};color:${text}">${SIZES.map(
        (size) =>
          `<span class="tile" style="font-size:${size / 1.35}px"><img src="${src}" alt=""></span>`,
      ).join("")} <span style="font-size:13px">${html(name)}</span><small>${theme}</small></td>`,
  ).join("");
  return `<tr><th>${html(name)}<br><a href="${html(source)}">${html(file)}</a><br><small>${html(license)}</small></th><td class="bare"><img src="${src}" alt=""></td>${tiles}</tr>`;
});

mkdirSync(dirname(resolve(out)), { recursive: true });
writeFileSync(
  resolve(out),
  `<!doctype html>
<meta charset="utf-8">
<title>Logos (${rows.length})</title>
<style>
  body { margin: 24px; font: 14px system-ui, sans-serif; color: #1f2328; }
  table { border-collapse: collapse; }
  th, td { padding: 12px 16px; border-bottom: 1px solid #d0d7de; text-align: left; vertical-align: middle; }
  th { font-weight: 600; max-width: 260px; }
  th small, td small { display: block; color: #6e7781; font-weight: 400; margin-top: 4px; }
  .bare { width: 64px; }
  .bare img { display: block; max-width: 64px; max-height: 64px; margin: auto;
    outline: 1px dashed #d0d7de; }
  /* As styles.css's .logo. */
  .tile { display: inline-block; box-sizing: border-box; width: 1.35em; height: 1.35em;
    padding: 0 0.175em; margin-right: 0.35em; border-radius: 0.3em; background: #fff;
    box-shadow: inset 0 0 0 1px rgb(0 0 0 / 0.08); vertical-align: -0.35em; }
  .tile > img { position: relative; top: 50%; display: block; width: auto; height: auto;
    max-width: 1em; max-height: 1em; margin: 0 auto; border-radius: 0.15em;
    transform: translateY(-50%); }
</style>
<h1>Logos (${rows.length})</h1>
<table>${rows.join("\n")}</table>
`,
);
console.log(`${rows.length} logos: ${resolve(out)}`);
