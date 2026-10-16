import { useMemo } from "preact/hooks";
import { affiliationCoverage, countOf } from "../format";
import { type EntityKind, severalPeople } from "../graph";
import { type RankingMetric, rankEntities } from "../rankings";
import type { Paper } from "../types";
import type { RankKind } from "../url-state";
import type { CountryMetric } from "../world";
import { ChevronIcon, GlobeIcon } from "./icons";
import { LazyWorldMap } from "./LazyWorldMap";
import { Segmented } from "./Segmented";

const SHOWN = 100;
const KIND_NAMES: Record<RankKind, string> = {
  institution: "Institutions",
  author: "Authors",
  country: "Countries",
};

interface Props {
  category: string;
  /** The papers ranked: those of the period or archive year matching the search and filters. */
  papers: Paper[];
  citations: ReadonlyMap<string, number>;
  citationsNote: string | undefined;
  /** Whether the papers are highly cited ones: citations then rank them by default. */
  archived: boolean;
  /** Institutions, authors or countries, as the URL says (`?rank=`, SRCH-13, UX-41). */
  kind: RankKind;
  /** By papers or citations, and for countries per million people or impact (`?metric=`). */
  metric: CountryMetric | null;
  /** Show the papers of an institution or author. */
  onEntity: (kind: EntityKind, name: string) => void;
}

/**
 * Recent papers are rarely cited yet: they rank by papers unless asked otherwise. Only
 * countries rank by people or impact.
 */
function metricOf(metric: CountryMetric | null, archived: boolean): RankingMetric {
  return metric === "papers" || metric === "citations" ? metric : archived ? "citations" : "papers";
}

/** The countries' metric (UX-41): impact only for highly cited papers, which have citations. */
function countryMetricOf(metric: CountryMetric | null, archived: boolean): CountryMetric {
  return metric === null || (metric === "impact" && !archived)
    ? metricOf(metric, archived)
    : metric;
}

/**
 * The way to the world map in Rankings' sidebar (UX-41), drawn as a card: where the papers
 * come from, countries ranked; pressed again, back to the institutions.
 */
export function WorldMapButton(props: { active: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      class="world-map-button"
      aria-pressed={props.active}
      onClick={props.onToggle}
    >
      <span class="world-map-button__globe" aria-hidden="true">
        <GlobeIcon />
      </span>
      <span class="world-map-button__label">
        <span>World map</span>
        <span class="world-map-button__detail">
          {props.active ? "Back to the institutions" : "Where the papers come from"}
        </span>
      </span>
      <span class="world-map-button__chevron" aria-hidden="true">
        <ChevronIcon up={false} />
      </span>
    </button>
  );
}
/** What Rankings ranks and how, in the list's header (UX-33), as the lists' order. */
export function RankingsControls(props: {
  archived: boolean;
  kind: RankKind;
  metric: CountryMetric | null;
  onKind: (kind: RankKind) => void;
  onMetric: (metric: CountryMetric) => void;
}) {
  const countries = props.kind === "country";
  return (
    <div class="rankings__controls">
      <div class="rankings__group">
        <span class="muted" aria-hidden="true">
          Rank
        </span>
        <Segmented
          legend="Rank"
          options={[
            ["institution", KIND_NAMES.institution],
            ["author", KIND_NAMES.author],
            ["country", KIND_NAMES.country],
          ]}
          value={props.kind}
          onChange={props.onKind}
        />
      </div>
      <div class="rankings__group">
        <span class="muted" aria-hidden="true">
          By
        </span>
        <Segmented<CountryMetric>
          legend="By"
          options={[
            ["papers", "Papers"],
            ["citations", "Citations"],
            ...(countries ? ([["per-million", "Per million people"]] as const) : []),
            ...(countries && props.archived ? ([["impact", "Impact"]] as const) : []),
          ]}
          value={
            countries
              ? countryMetricOf(props.metric, props.archived)
              : metricOf(props.metric, props.archived)
          }
          onChange={props.onMetric}
          titles={{
            "per-million": "Papers per million people, for countries of a million people or more",
            impact: "Citations per paper over the world's, for countries of 10 papers or more",
          }}
        />
      </div>
    </div>
  );
}

/** Institutions, authors or countries of the papers shown, by papers or citations. */
export function Rankings(props: Props) {
  return props.kind === "country" ? (
    <LazyWorldMap
      category={props.category}
      papers={props.papers}
      citations={props.citations}
      metric={countryMetricOf(props.metric, props.archived)}
      archived={props.archived}
    />
  ) : (
    <EntityRankings {...props} kind={props.kind} />
  );
}

/** Institutions or authors of the papers shown, by number of papers or citations. */
function EntityRankings(props: Props & { kind: EntityKind }) {
  const { papers, citations, citationsNote, archived, kind, onEntity } = props;
  const metric = metricOf(props.metric, archived);
  const ranked = useMemo(
    () => rankEntities(papers, kind, metric, citations),
    [papers, kind, metric, citations],
  );
  const affiliated = useMemo(
    () => papers.filter((paper) => (paper.affiliations ?? []).length > 0).length,
    [papers],
  );

  return (
    <section class="rankings" aria-label="Rankings">
      <p class="muted rankings__note">
        {countOf(ranked.length, kind)} in{" "}
        {papers.length === 1 ? "this paper" : `these ${countOf(papers.length, "paper")}`}.
        {/* The ⓘ says it always; the table, when it ranks a minority of the papers. */}
        {kind === "institution" &&
          affiliated < papers.length / 2 &&
          ` ${affiliationCoverage(affiliated, papers.length)}.`}
      </p>
      {ranked.length > 0 && (
        <table class="rankings__table">
          <caption class="visually-hidden">
            {KIND_NAMES[kind]} of the papers shown, by {metric}
          </caption>
          <thead>
            <tr>
              <th scope="col" class="rankings__rank">
                #
              </th>
              <th scope="col">{kind === "institution" ? "Institution" : "Author"}</th>
              <th scope="col" class="rankings__number">
                Papers
              </th>
              <th scope="col" class="rankings__number" title={citationsNote}>
                Citations
              </th>
              <th scope="col">Most cited paper</th>
            </tr>
          </thead>
          <tbody>
            {ranked.slice(0, SHOWN).map((entity, index) => (
              <tr key={entity.id}>
                <td class="rankings__rank">{index + 1}</td>
                <th scope="row">
                  <button
                    type="button"
                    class="link-button"
                    title="Show their papers"
                    onClick={() => onEntity(entity.kind, entity.name)}
                  >
                    {entity.name}
                  </button>
                  {entity.people && (
                    <span class="muted" title={severalPeople(entity.people)}>
                      {" "}
                      · {entity.people} people?
                    </span>
                  )}
                </th>
                <td class="rankings__number">{entity.papers.toLocaleString()}</td>
                <td class="rankings__number">{entity.citations.toLocaleString()}</td>
                <td class="rankings__top">
                  <a href={entity.top.abs_url} target="_blank" rel="noopener noreferrer">
                    {entity.top.title}
                  </a>
                  {entity.topCitations !== undefined && (
                    <span class="muted"> · {entity.topCitations.toLocaleString()}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ranked.length > SHOWN && (
        <p class="muted rankings__note">
          The first {SHOWN} of {ranked.length.toLocaleString()}: narrow the search to see others.
        </p>
      )}
    </section>
  );
}
