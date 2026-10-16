/**
 * Writes `src/geo/world.json`, the map of Rankings' world map (UX-41), from Natural Earth's
 * countries (public domain), downloaded once by hand:
 *
 *   node tooling/world-map.ts ne_110m_admin_0_countries.geojson ne_50m_admin_0_countries.geojson
 *
 * The 1:110m countries are the shapes, as TopoJSON (their shared borders once, coordinates
 * quantized: 92 kB instead of 840, 30 gzipped), without Antarctica, where no paper comes from. The
 * 1:50m file gives every country's name and population, and a point for those too small
 * for the 1:110m shapes: Hong Kong, Singapore and Macao hold 8% of cs.CV's papers placed.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { topology } from "topojson-server";

interface Properties {
  ISO_A2_EH: string;
  NAME: string;
  POP_EST: number;
  POP_YEAR: number;
  LABEL_X: number;
  LABEL_Y: number;
}

type Countries = FeatureCollection<Geometry, Properties>;

const [shapesPath, factsPath] = process.argv.slice(2);
if (!shapesPath || !factsPath) {
  throw new Error("usage: node tooling/world-map.ts <1:110m countries> <1:50m countries>");
}
const read = (path: string) => JSON.parse(readFileSync(path, "utf8")) as Countries;
// A code Natural Earth leaves out ("-99": Somaliland) names no country of the store.
const coded = (code: string) => /^[A-Z]{2}$/.test(code);

const shapes = read(shapesPath).features.filter(({ properties }) => properties.ISO_A2_EH !== "AQ");
const drawn = new Set(shapes.map(({ properties }) => properties.ISO_A2_EH));
const countries: FeatureCollection = {
  type: "FeatureCollection",
  features: shapes.map(
    ({ geometry, properties }): Feature => ({
      type: "Feature",
      id: coded(properties.ISO_A2_EH) ? properties.ISO_A2_EH : "",
      properties: {},
      geometry,
    }),
  ),
};

// A country's territories share its code (Ashmore and Cartier Islands are "AU"): the most
// populous of them is the country.
const byCode = new Map<string, Properties>();
for (const { properties } of read(factsPath).features) {
  const known = byCode.get(properties.ISO_A2_EH);
  if (coded(properties.ISO_A2_EH) && (!known || properties.POP_EST > known.POP_EST)) {
    byCode.set(properties.ISO_A2_EH, properties);
  }
}
const facts = Object.fromEntries(
  [...byCode.values()]
    .map((country) => [
      country.ISO_A2_EH,
      {
        name: country.NAME,
        population: country.POP_EST,
        ...(drawn.has(country.ISO_A2_EH)
          ? {}
          : { point: [Number(country.LABEL_X.toFixed(2)), Number(country.LABEL_Y.toFixed(2))] }),
      },
    ])
    .sort(([a], [b]) => String(a).localeCompare(String(b))),
);

const output = resolve(import.meta.dirname, "..", "src", "geo", "world.json");
writeFileSync(
  output,
  `${JSON.stringify({
    source: "Natural Earth 5.1.2, public domain; populations estimated mostly in 2019",
    topology: topology({ countries }, 1e4),
    facts,
  })}\n`,
);
console.log(`${output}: ${shapes.length} shapes, ${Object.keys(facts).length} countries`);
