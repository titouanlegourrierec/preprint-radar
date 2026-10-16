import { useMemo } from "preact/hooks";
import { affiliationCoverage, countOf } from "../format";
import { type EntityKind, severalPeople } from "../graph";
import { type RankingMetric, rankEntities } from "../rankings";
import type { Paper } from "../types";
import { Segmented } from "./Segmented";

const SHOWN = 100;
const KIND_NAMES: Record<EntityKind, string> = { institution: "Institutions", author: "Authors" };

interface Props {
  /** The papers ranked: those of the period or archive year matching the search and filters. */
  papers: Paper[];
  citations: ReadonlyMap<string, number>;
  citationsNote: string | undefined;
  /** Whether the papers are highly cited ones: citations then rank them by default. */
  archived: boolean;
  /** Institutions or authors, as the URL says (`?rank=`, SRCH-13). */
  kind: EntityKind;
  /** By papers or citations (`?metric=`), `null` for the default. */
  metric: RankingMetric | null;
  /** Show the papers of an institution or author. */
  onEntity: (kind: EntityKind, name: string) => void;
}

/** Recent papers are rarely cited yet: they rank by papers unless asked otherwise. */
function metricOf(metric: RankingMetric | null, archived: boolean): RankingMetric {
  return metric ?? (archived ? "citations" : "papers");
}

/** What Rankings ranks and how, in the list's header (UX-33), as the lists' order. */
export function RankingsControls(props: {
  archived: boolean;
  kind: EntityKind;
  metric: RankingMetric | null;
  onKind: (kind: EntityKind) => void;
  onMetric: (metric: RankingMetric) => void;
}) {
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
          ]}
          value={props.kind}
          onChange={props.onKind}
        />
      </div>
      <div class="rankings__group">
        <span class="muted" aria-hidden="true">
          By
        </span>
        <Segmented
          legend="By"
          options={[
            ["papers", "Papers"],
            ["citations", "Citations"],
          ]}
          value={metricOf(props.metric, props.archived)}
          onChange={props.onMetric}
        />
      </div>
    </div>
  );
}

/** Institutions and authors of the papers shown, by number of papers or citations. */
export function Rankings(props: Props) {
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
