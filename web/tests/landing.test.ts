import { describe, expect, it } from "vitest";
import { LANDING_BUDGET, landingAssets, landingReport } from "../tooling/landing";

describe("the landing page's budget", () => {
  it("counts what index.html loads, once each", () => {
    const html = [
      '<script src="./theme.js"></script>',
      '<script type="module" crossorigin src="./assets/index-a1.js"></script>',
      '<link rel="modulepreload" crossorigin href="./assets/vendor-b2.js">',
      '<link rel="stylesheet" crossorigin href="./assets/index-c3.css">',
      '<link rel="preload" href="./data/index.json" as="fetch" crossorigin />',
      '<link rel="stylesheet" href="./assets/index-c3.css">',
    ].join("\n");

    // Not the data, nor what the app imports on demand (GraphView), which index.html omits.
    expect(landingAssets(html)).toEqual([
      "assets/index-a1.js",
      "assets/vendor-b2.js",
      "assets/index-c3.css",
    ]);
  });

  it("sums their gzipped sizes into the line the build prints", () => {
    const files = new Map([
      ["index.html", "<html></html>"],
      ["assets/index-a1.js", "x".repeat(10_000)],
    ]);

    // A tenth of each text, as a stand-in for gzip.
    const { bytes, line } = landingReport(files, (text) => Math.round(text.length / 10));

    expect(bytes).toBe(1 + 1000);
    expect(bytes).toBeLessThan(LANDING_BUDGET);
    expect(line).toBe(
      "Landing page: 1.0 kB gzipped of 100.0 kB (index.html 0.0 kB, assets/index-a1.js 1.0 kB)",
    );
  });
});
