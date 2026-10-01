import { describe, expect, it } from "vitest";
import { thirdPartyLoads } from "../tooling/third-party";

describe("thirdPartyLoads", () => {
  it.each([
    ["index.html", '<script src="https://cdn.example.org/a.js"></script>'],
    ["index.html", "<link rel=stylesheet href=//fonts.example.org/css>"],
    ["assets/index.css", 'body{background:url("https://example.org/a.png")}'],
    ["assets/index.css", '@import "https://fonts.example.org/css";'],
    ["assets/index.js", 'fetch("https://example.org/track")'],
    ["assets/index.js", "img.src=`https://example.org/pixel.gif`"],
  ])("finds the load in %s: %s", (fileName, code) => {
    expect(thirdPartyLoads(fileName, code)).toHaveLength(1);
  });

  it.each([
    ["index.html", '<a href="https://arxiv.org">arXiv</a>'],
    // The icon is a data URI holding an SVG namespace, not a load.
    [
      "index.html",
      `<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'>" />`,
    ],
    ["index.html", '<script type="module" src="./assets/index.js"></script>'],
    ["assets/index.js", 'const a={href:"https://arxiv.org/abs/"+id};fetch("./data/index.json")'],
    ["data/index.json", '{"url": "https://example.org"}'],
  ])("lets %s through: %s", (fileName, code) => {
    expect(thirdPartyLoads(fileName, code)).toEqual([]);
  });
});
