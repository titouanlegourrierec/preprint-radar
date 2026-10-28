import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { loadCountries } from "../data";
import { countOf } from "../format";
import { useListId, useReorder } from "../hooks/use-reorder";
import { LOCALE } from "../locale";
import { loadMapGlobe, saveMapGlobe } from "../preferences";
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
import { Flag } from "./Flag";
import { InfoButton } from "./InfoButton";
import { MapFrame, nameOf, WORLD } from "./MapFrame";
import { RankCell, shareOf } from "./RankCell";
import { Segmented } from "./Segmented";
import { SortHeader } from "./SortHeader";

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

/** The table's columns of figures, in order; impact for highly cited papers only. */
const COLUMNS: readonly CountryMetric[] = ["papers", "citations", "per-million", "impact"];

/** A value of a metric as the map says it. */
function formatValue(value: number | null, metric: CountryMetric): string {
  if (value === null) return "—";
  if (metric === "impact") return `${value.toFixed(2)}×`;
  if (metric === "per-million") return value.toLocaleString(LOCALE, { maximumFractionDigits: 2 });
  return formatShare(value);
}

/** The legend's label of each class: "< 5", "5–20", …, "≥ 2,000". */
function classLabels(thresholds: readonly number[], metric: CountryMetric): string[] {
  const show = (value: number) =>
    metric === "impact" ? `${value}×` : value.toLocaleString(LOCALE, { maximumFractionDigits: 2 });
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
  /** Rank by another metric: a column's header pressed (UX-42). */
  onMetric: (metric: CountryMetric) => void;
  /** Show the papers of a country, the one pinned (PROD-22). */
  onCountry?: ((code: string) => void) | undefined;
}

/**
 * Where the papers shown come from (UX-41): a world map of the countries of their
 * institutions, colored by papers, citations, papers per million people or impact, with
 * a tooltip on each country (its values and institutions with most papers), pinned by a
 * click, flat or a globe (UX-43); then the countries as a table, the map's values for
 * those who do not see it, ranked by a column's header. Loaded with its chunk, only when
 * Rankings shows countries.
 */
export function WorldMap({
  category,
  papers,
  citations,
  metric,
  archived,
  onMetric,
  onCountry,
}: Props) {
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
  const fillOf = useCallback(
    (code: string): string => {
      const country = byCode.get(code);
      const value = country ? metricValue(country, metric) : null;
      if (value === null) return "world-map__fill--none";
      return `world-map__fill--${metric === "impact" ? "d" : "s"}${classOf(value, thresholds)}`;
    },
    [byCode, metric, thresholds],
  );
  // The countries too small for the map's shapes, a dot each where they have papers.
  const dots = useMemo(
    () => Object.keys(WORLD.facts).filter((code) => WORLD.facts[code]?.point && byCode.has(code)),
    [byCode],
  );

  // The country pinned by a click (a tap), or from the table: its tooltip.
  const [pinned, setPinned] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  // Flat or a globe (UX-43), as this browser last showed it.
  const [globe, setGlobe] = useState(loadMapGlobe);
  const project = (view: "flat" | "globe") => {
    setGlobe(view === "globe");
    saveMapGlobe(view === "globe");
  };

  const ordered = stats ? byMetric(stats.countries, metric) : [];
  const listed = all ? ordered : ordered.slice(0, LISTED);
  // Rows glide to their new place when another metric ranks them (UX-62).
  const rows = useRef<HTMLTableSectionElement>(null);
  const moves = useReorder(
    rows,
    listed.map(({ code }) => code),
    metric,
    useListId(papers, "country"),
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

  // The first country's value of the metric ranked by, for each row's share of it (UX-60).
  const first = ordered[0] ? metricValue(ordered[0], metric) : null;
  const labels = classLabels(thresholds, metric);
  const pinnedCountry = pinned ? byCode.get(pinned) : undefined;
  return (
    <section class="world-map" aria-label="World map">
      <div class="world-map__card">
        <div class="world-map__head">
          <p>
            <strong>{METRIC_TITLES[metric]}</strong>
            <span class="muted">
              {countOf(stats.countries.length, "country", "countries")} ·{" "}
              {stats.placed.toLocaleString(LOCALE)} of {countOf(stats.total, "paper")} placed (
              {stats.total ? Math.round((100 * stats.placed) / stats.total) : 0}%)
            </span>
          </p>
          <div class="world-map__tools">
            <Segmented
              legend="Projection"
              options={[
                ["flat", "Flat"],
                ["globe", "Globe"],
              ]}
              value={globe ? "globe" : "flat"}
              onChange={project}
              titles={{
                flat: "The whole world at once, each country at its size",
                globe: "A globe to turn",
              }}
            />
            <InfoButton label="About the map" end>
              <p>
                {`Countries known for ${stats.placed.toLocaleString(LOCALE)} of ${countOf(stats.total, "paper")} (${
                  stats.total ? Math.round((100 * stats.placed) / stats.total) : 0
                }%): those of their institutions with a ROR id, which OpenAlex places; the others count for no country.`}
              </p>
              <p>
                A paper of several countries counts a share for each: half for each of two, so that
                a collaboration is not counted twice. Its citations are shared the same way.
              </p>
              <p>
                Papers per million people leave out countries under a million people. Impact is the
                citations per paper of a country over those of all the papers placed, for countries
                of {MIN_IMPACT_PAPERS} papers or more: 1.2× is a fifth above the world's; it means
                most for highly cited papers, recent ones having few citations yet.
              </p>
              <p>
                {`Map and populations from Natural Earth (public domain), estimated mostly in 2019; Hong Kong, Singapore and other countries too small for the map are its dots.`}
              </p>
              <p>
                {`Zoom with the buttons, a pinch, or the wheel holding Ctrl or ⌘ (the wheel alone scrolls the page); drag to move the map or turn the globe. The flat map shows every country at its size, the globe half of them at a time.`}
              </p>
            </InfoButton>
          </div>
        </div>
        <MapFrame
          key={globe ? "globe" : "flat"}
          globe={globe}
          label={`World map of the countries of these papers, by ${METRIC_NAMES[metric]}: ${ordered
            .slice(0, 5)
            .map(
              (country) =>
                `${nameOf(country.code)} ${formatValue(metricValue(country, metric), metric)}`,
            )
            .join(", ")}. The table below lists every country.`}
          fillOf={fillOf}
          dots={dots}
          pinned={pinned}
          onPin={setPinned}
          lead={ordered[0]?.code ?? null}
          tip={(code) => {
            const tip = byCode.get(code);
            return (
              <>
                <strong>
                  {tip ? formatValue(metricValue(tip, metric), metric) : "—"}
                  <span> {tip ? METRIC_NAMES[metric] : "no paper placed"}</span>
                </strong>
                <span class="world-map__tip-name">
                  <Flag code={code} />
                  {nameOf(code)}
                </span>
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
              </>
            );
          }}
        />
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
      {/* A country pinned, on the map or in the table, offers its papers (PROD-22). */}
      {pinnedCountry && onCountry && (
        <p class="world-map__pinned">
          <button type="button" class="link-button" onClick={() => onCountry(pinnedCountry.code)}>
            Show the papers of <Flag code={pinnedCountry.code} />
            {nameOf(pinnedCountry.code)}
          </button>
        </p>
      )}

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
            <SortHeader metric="papers" active={metric} name="Papers" onSort={onMetric} />
            <SortHeader metric="citations" active={metric} name="Citations" onSort={onMetric} />
            <SortHeader
              metric="per-million"
              active={metric}
              name="Per million people"
              onSort={onMetric}
            />
            {archived && (
              <SortHeader metric="impact" active={metric} name="Impact" onSort={onMetric} />
            )}
            <th scope="col">Institutions with most papers</th>
          </tr>
        </thead>
        <tbody ref={rows}>
          {listed.map((country: CountryStats, index) => (
            <tr
              key={country.code}
              data-key={country.code}
              class={pinnedCountry === country ? "world-map__row--pinned" : undefined}
            >
              <RankCell rank={index + 1} move={moves?.get(country.code)} />
              <th scope="row">
                <button
                  type="button"
                  class="link-button"
                  aria-pressed={pinned === country.code}
                  title="Show it on the map"
                  onClick={() => setPinned(pinned === country.code ? null : country.code)}
                >
                  <Flag code={country.code} />
                  {nameOf(country.code)}
                </button>
              </th>
              {COLUMNS.filter((column) => column !== "impact" || archived).map((column) => (
                <td
                  key={column}
                  class={`rankings__number${column === metric ? " rankings__number--ranked" : ""}`}
                  style={
                    column === metric ? shareOf(metricValue(country, column), first) : undefined
                  }
                >
                  {formatValue(metricValue(country, column), column)}
                </td>
              ))}
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
