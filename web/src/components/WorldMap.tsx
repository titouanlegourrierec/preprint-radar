import { geoEqualEarth, geoPath } from "d3-geo";
import type { FeatureCollection, GeoJsonProperties, Geometry } from "geojson";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import { loadCountries } from "../data";
import { countOf } from "../format";
import world from "../geo/world.json";
import type { Paper } from "../types";
import {
  byMetric,
  type CountriesFile,
  type CountryMetric,
  type CountryStats,
  classOf,
  formatShare,
  IMPACT_THRESHOLDS,
  logThresholds,
  MIN_IMPACT_PAPERS,
  metricValue,
  worldStats,
} from "../world";
import { InfoButton } from "./InfoButton";

interface WorldFile {
  source: string;
  topology: Topology<{ countries: GeometryCollection }>;
  /** Each country's name and population, and a point for one too small to draw. */
  facts: Record<string, { name: string; population: number; point?: [number, number] }>;
}

const WORLD = world as unknown as WorldFile;
const WIDTH = 960;
/** The volume metrics' classes, light to dark (`--map-s0`…); impact has five (`--map-d0`…). */
const CLASSES = 6;
/** Countries listed before "Show all". */
const LISTED = 20;

const METRIC_NAMES: Record<CountryMetric, string> = {
  papers: "papers",
  citations: "citations",
  "per-million": "per million people",
  impact: "impact",
};
const METRIC_TITLES: Record<CountryMetric, string> = {
  papers: "Papers by country",
  citations: "Citations by country",
  "per-million": "Papers per million people",
  impact: "Impact: citations per paper over the world's",
};

/**
 * The countries' shapes in the Equal Earth projection, which keeps their areas (a globe
 * would hide half of them), projected once: Natural Earth's 1:110m countries without
 * Antarctica, and a point for each country too small for them (Hong Kong, Singapore).
 */
const MAP = (() => {
  const countries = feature(WORLD.topology, WORLD.topology.objects.countries) as FeatureCollection<
    Geometry,
    GeoJsonProperties
  >;
  const projection = geoEqualEarth().fitWidth(WIDTH, countries);
  const path = geoPath(projection);
  const height = Math.ceil(path.bounds(countries)[1][1]);
  const shapes = countries.features.map((country) => ({
    code: String(country.id ?? ""),
    d: path(country) ?? "",
    center: path.centroid(country),
  }));
  const points = Object.entries(WORLD.facts).flatMap(([code, facts]) => {
    const at = facts.point ? projection(facts.point) : null;
    return at ? [{ code, center: at }] : [];
  });
  return { height, shapes, points };
})();

const nameOf = (code: string) => WORLD.facts[code]?.name ?? code;

/** A value of a metric as the map says it. */
function formatValue(value: number | null, metric: CountryMetric): string {
  if (value === null) return "—";
  if (metric === "impact") return `${value.toFixed(2)}×`;
  if (metric === "per-million")
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return formatShare(value);
}

/** The legend's label of each class: "< 5", "5–20", …, "≥ 2,000". */
function classLabels(thresholds: readonly number[], metric: CountryMetric): string[] {
  const show = (value: number) =>
    metric === "impact"
      ? `${value}×`
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return [
    `< ${show(thresholds[0] ?? 0)}`,
    ...thresholds.slice(1).map((value, index) => `${show(thresholds[index] ?? 0)}–${show(value)}`),
    `≥ ${show(thresholds.at(-1) ?? 0)}`,
  ];
}

interface Props {
  category: string;
  /** The papers ranked: those of the period or years, the search and the filters. */
  papers: readonly Paper[];
  citations: ReadonlyMap<string, number>;
  metric: CountryMetric;
  /** Highly cited papers, whose citations say something: impact is offered then. */
  archived: boolean;
}

/**
 * Where the papers shown come from (UX-41): a world map of the countries of their
 * institutions, colored by papers, citations, papers per million people or impact, with
 * a tooltip on each country (its values and institutions with most papers), pinned by a
 * click; then the countries as a table, the map's values for those who do not see it.
 * Loaded with its chunk, only when Rankings shows countries.
 */
export function WorldMap({ category, papers, citations, metric, archived }: Props) {
  const [file, setFile] = useState<CountriesFile | null | undefined>(undefined);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    setFile(undefined);
    setFailed(false);
    loadCountries(category)
      .then((loaded) => live && setFile(loaded))
      .catch((error: unknown) => {
        console.warn("Could not load the countries", error);
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [category]);

  const stats = useMemo(() => {
    if (!file) return null;
    const institutions = file.institutions;
    return worldStats(
      papers,
      (id) => institutions[id],
      citations,
      (code) => WORLD.facts[code],
    );
  }, [file, papers, citations]);
  const byCode = useMemo(
    () => new Map((stats?.countries ?? []).map((country) => [country.code, country])),
    [stats],
  );
  const thresholds = useMemo(
    () =>
      metric === "impact"
        ? [...IMPACT_THRESHOLDS]
        : logThresholds(
            (stats?.countries ?? []).map((country) => metricValue(country, metric) ?? 0),
            CLASSES,
          ),
    [stats, metric],
  );
  const fill = (code: string): string => {
    const country = byCode.get(code);
    const value = country ? metricValue(country, metric) : null;
    if (value === null) return "world-map__fill--none";
    return `world-map__fill--${metric === "impact" ? "d" : "s"}${classOf(value, thresholds)}`;
  };

  // The country under the pointer, or pinned by a click (a tap): its tooltip.
  const [hovered, setHovered] = useState<{ code: string; x: number; y: number } | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const frame = useRef<HTMLDivElement>(null);
  // The country under the pointer: the shape or dot it is over (`data-code`).
  const codeAt = (target: EventTarget | null): string | null =>
    target instanceof Element
      ? (target.closest<SVGElement>("[data-code]")?.dataset.code ?? null)
      : null;
  const pointAt = (event: PointerEvent) => {
    const code = codeAt(event.target);
    const box = frame.current?.getBoundingClientRect();
    if (code === null || !box) setHovered(null);
    else setHovered({ code, x: event.clientX - box.left, y: event.clientY - box.top });
  };
  // A pinned country's tooltip sits at its center, as the frame scales the map.
  const pinnedAt = (code: string) => {
    const center =
      MAP.shapes.find((shape) => shape.code === code)?.center ??
      MAP.points.find((point) => point.code === code)?.center;
    const width = frame.current?.clientWidth ?? WIDTH;
    return center ? { code, x: (center[0] * width) / WIDTH, y: (center[1] * width) / WIDTH } : null;
  };
  const shown = hovered ?? (pinned ? pinnedAt(pinned) : null);

  // The shapes are drawn again only when their colors or the pinned country change, not
  // as the pointer moves over them.
  const drawing = useMemo(
    () => (
      <svg
        class="world-map__svg"
        viewBox={`0 0 ${WIDTH} ${MAP.height}`}
        role="img"
        aria-label={`World map of the countries of these papers, by ${METRIC_NAMES[metric]}: ${byMetric(
          stats?.countries ?? [],
          metric,
        )
          .slice(0, 5)
          .map(
            (country) =>
              `${nameOf(country.code)} ${formatValue(metricValue(country, metric), metric)}`,
          )
          .join(", ")}. The table below lists every country.`}
      >
        {/* Hatched where the metric says nothing, apart from any of its colors. */}
        <defs>
          <pattern
            id="world-map-hatch"
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect class="world-map__hatch-ground" width="4" height="4" />
            <rect class="world-map__hatch-line" width="1.4" height="4" />
          </pattern>
        </defs>
        {MAP.shapes.map(({ code, d }, index) => (
          <path
            key={code || `shape-${index}`}
            d={d}
            class={`world-map__shape ${fill(code)}${pinned === code ? " world-map__shape--pinned" : ""}`}
            data-code={code || undefined}
          />
        ))}
        {MAP.points
          .filter(({ code }) => byCode.has(code))
          .map(({ code, center }) => (
            <circle
              key={code}
              cx={center[0]}
              cy={center[1]}
              r={5}
              class={`world-map__point ${fill(code)}${pinned === code ? " world-map__shape--pinned" : ""}`}
              data-code={code}
            />
          ))}
      </svg>
    ),
    [stats, metric, thresholds, pinned],
  );

  if (failed) {
    return (
      <p class="notice notice--error" role="alert">
        The countries of the institutions could not be loaded.
      </p>
    );
  }
  if (file === undefined) {
    return (
      <p class="notice" role="status">
        Loading the map…
      </p>
    );
  }
  if (file === null || stats === null) {
    return (
      <p class="notice">
        The countries of the institutions are asked for every day, with the papers: they are not
        there yet.
      </p>
    );
  }

  const ordered = byMetric(stats.countries, metric);
  const listed = all ? ordered : ordered.slice(0, LISTED);
  const labels = classLabels(thresholds, metric);
  const tip = shown ? byCode.get(shown.code) : undefined;
  const pinnedCountry = pinned ? byCode.get(pinned) : undefined;
  return (
    <section class="world-map" aria-label="World map">
      <div class="world-map__card">
        <div class="world-map__head">
          <p>
            <strong>{METRIC_TITLES[metric]}</strong>
            <span class="muted">
              {countOf(stats.countries.length, "country", "countries")} ·{" "}
              {stats.placed.toLocaleString()} of {countOf(stats.total, "paper")} placed (
              {stats.total ? Math.round((100 * stats.placed) / stats.total) : 0}%)
            </span>
          </p>
          <InfoButton label="About the map" end>
            <p>
              {`Countries known for ${stats.placed.toLocaleString()} of ${countOf(stats.total, "paper")} (${
                stats.total ? Math.round((100 * stats.placed) / stats.total) : 0
              }%): those of their institutions with a ROR id, which OpenAlex places; the others count for no country.`}
            </p>
            <p>
              A paper of several countries counts a share for each: half for each of two, so that a
              collaboration is not counted twice. Its citations are shared the same way.
            </p>
            <p>
              Papers per million people leave out countries under a million people. Impact is the
              citations per paper of a country over those of all the papers placed, for countries of{" "}
              {MIN_IMPACT_PAPERS} papers or more: 1.2× is a fifth above the world's; it means most
              for highly cited papers, recent ones having few citations yet.
            </p>
            <p>
              {`Map and populations from Natural Earth (public domain), estimated mostly in 2019; Hong Kong, Singapore and other countries too small for the map are its dots.`}
            </p>
          </InfoButton>
        </div>
        {/* The pointer's tooltips; the table below holds the same values for the keyboard and
            screen readers. */}
        <div
          class="world-map__frame"
          ref={frame}
          onPointerMove={pointAt}
          onPointerLeave={() => setHovered(null)}
          // A click or a tap pins a country's tooltip; the table's buttons do from the keyboard.
          onPointerUp={(event) => {
            const code = codeAt(event.target);
            if (code !== null) setPinned(pinned === code ? null : code);
          }}
        >
          {drawing}
          {shown && (
            <div
              class={`world-map__tip${shown.x > (frame.current?.clientWidth ?? WIDTH) / 2 ? " world-map__tip--left" : ""}`}
              style={{ left: `${shown.x}px`, top: `${shown.y}px` }}
            >
              <strong>
                {tip ? formatValue(metricValue(tip, metric), metric) : "—"}
                <span> {tip ? METRIC_NAMES[metric] : "no paper placed"}</span>
              </strong>
              <span class="world-map__tip-name">{nameOf(shown.code)}</span>
              {tip && (
                <dl>
                  {(["papers", "citations", "per-million", "impact"] as const)
                    .filter((other) => other !== metric && (other !== "impact" || archived))
                    .map((other) => (
                      <div key={other}>
                        <dt>{METRIC_NAMES[other]}</dt>
                        <dd>{formatValue(metricValue(tip, other), other)}</dd>
                      </div>
                    ))}
                </dl>
              )}
              {tip && tip.institutions.length > 0 && (
                <p>{tip.institutions.map(({ name }) => name).join(" · ")}</p>
              )}
            </div>
          )}
        </div>
        <ul class="world-map__legend" aria-label={`Legend: ${METRIC_NAMES[metric]}`}>
          {labels.map((label, index) => (
            <li key={label} class="world-map__key">
              <i
                class={`world-map__swatch world-map__fill--${metric === "impact" ? "d" : "s"}${index}`}
                aria-hidden="true"
              />
              {label}
            </li>
          ))}
          <li class="world-map__key">
            <i class="world-map__swatch world-map__fill--none" aria-hidden="true" />
            {metric === "impact" || metric === "per-million" ? "Not said" : "No paper placed"}
          </li>
        </ul>
      </div>

      <table class="rankings__table world-map__table">
        <caption class="visually-hidden">
          The countries of the papers shown, by {METRIC_NAMES[metric]}
        </caption>
        <thead>
          <tr>
            <th scope="col" class="rankings__rank">
              #
            </th>
            <th scope="col">Country</th>
            <th scope="col" class="rankings__number">
              Papers
            </th>
            <th scope="col" class="rankings__number">
              Citations
            </th>
            <th scope="col" class="rankings__number">
              Per million people
            </th>
            {archived && (
              <th scope="col" class="rankings__number">
                Impact
              </th>
            )}
            <th scope="col">Institutions with most papers</th>
          </tr>
        </thead>
        <tbody>
          {listed.map((country: CountryStats, index) => (
            <tr
              key={country.code}
              class={pinnedCountry === country ? "world-map__row--pinned" : undefined}
            >
              <td class="rankings__rank">{index + 1}</td>
              <th scope="row">
                <button
                  type="button"
                  class="link-button"
                  aria-pressed={pinned === country.code}
                  title="Show it on the map"
                  onClick={() => setPinned(pinned === country.code ? null : country.code)}
                >
                  {nameOf(country.code)}
                </button>
              </th>
              <td class="rankings__number">{formatShare(country.papers)}</td>
              <td class="rankings__number">{formatShare(country.citations)}</td>
              <td class="rankings__number">{formatValue(country.perMillion, "per-million")}</td>
              {archived && (
                <td class="rankings__number">{formatValue(country.impact, "impact")}</td>
              )}
              <td class="rankings__top">
                {country.institutions.map(({ name }) => name).join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {ordered.length > LISTED && (
        <button type="button" class="link-button world-map__more" onClick={() => setAll(!all)}>
          {all
            ? `The first ${LISTED} only`
            : `Show all ${countOf(ordered.length, "country", "countries")}`}
        </button>
      )}
    </section>
  );
}
