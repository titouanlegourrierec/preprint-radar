import { useMemo } from "preact/hooks";
import { affiliationCoverage, countOf } from "../format";
import { type EntityKind, severalPeople } from "../graph";
import { rankEntities } from "../rankings";
import type { Paper } from "../types";
import type { RankKind } from "../url-state";
import type { CountryMetric } from "../world";
import { LazyWorldMap } from "./LazyWorldMap";
import { countryMetricOf, KIND_NAMES, metricOf } from "./RankingsControls";
import { SortHeader } from "./SortHeader";

const SHOWN = 100;

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
  /** Rank by another metric: a column's header pressed (UX-42). */
  onMetric: (metric: CountryMetric) => void;
  /** Show the papers of an institution or author. */
  onEntity: (kind: EntityKind, name: string) => void;
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
      onMetric={props.onMetric}
    />
  ) : (
    <EntityRankings {...props} kind={props.kind} />
  );
}

/** Institutions or authors of the papers shown, by number of papers or citations. */
function EntityRankings(props: Props & { kind: EntityKind }) {
  const { papers, citations, citationsNote, archived, kind, onMetric, onEntity } = props;
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
              <SortHeader metric="papers" active={metric} name="Papers" onSort={onMetric} />
              <SortHeader
                metric="citations"
                active={metric}
                name="Citations"
                title={citationsNote}
                onSort={onMetric}
              />
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
