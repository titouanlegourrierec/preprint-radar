import { useMemo, useState } from "preact/hooks";
import { type EntityKind, severalPeople } from "../graph";
import { type RankingMetric, rankEntities } from "../rankings";
import type { Paper } from "../types";

const SHOWN = 100;
const KIND_NAMES: Record<EntityKind, string> = { institution: "Institutions", author: "Authors" };

interface Props {
  /** The papers ranked: those of the period or archive year matching the search and filters. */
  papers: Paper[];
  citations: ReadonlyMap<string, number>;
  citationsNote: string | undefined;
  /** Whether the papers are highly cited ones: citations then rank them by default. */
  archived: boolean;
  /** Show the papers of an institution or author. */
  onEntity: (kind: EntityKind, name: string) => void;
}

/** Institutions and authors of the papers shown, by number of papers or citations. */
export function Rankings({ papers, citations, citationsNote, archived, onEntity }: Props) {
  const [kind, setKind] = useState<EntityKind>("institution");
  const [chosenMetric, setMetric] = useState<RankingMetric | null>(null);
  // Recent papers are rarely cited yet: they rank by papers unless asked otherwise.
  const metric = chosenMetric ?? (archived ? "citations" : "papers");
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
      <div class="rankings__controls">
        <Segmented
          label="Rank"
          options={[
            ["institution", KIND_NAMES.institution],
            ["author", KIND_NAMES.author],
          ]}
          value={kind}
          onChange={setKind}
        />
        <Segmented
          label="By"
          options={[
            ["papers", "Papers"],
            ["citations", "Citations"],
          ]}
          value={metric}
          onChange={setMetric}
        />
      </div>
      <p class="muted rankings__note">
        {ranked.length.toLocaleString()} {KIND_NAMES[kind].toLowerCase()} in these{" "}
        {papers.length.toLocaleString()} papers
        {kind === "institution" && ` (${affiliated.toLocaleString()} with known affiliations)`}.
        Citations are summed over their papers{archived ? "" : ": recent papers have few yet"}.
      </p>
      {ranked.length > 0 && (
        <table class="rankings__table">
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
                <td>
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
                </td>
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

function Segmented<T extends string>(props: {
  label: string;
  options: readonly (readonly [T, string])[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div class="rankings__group">
      <span class="muted" aria-hidden="true">
        {props.label}
      </span>
      <fieldset class="segmented">
        <legend class="visually-hidden">{props.label}</legend>
        {props.options.map(([value, name]) => (
          <button
            key={value}
            type="button"
            class={`segmented__option${props.value === value ? " segmented__option--active" : ""}`}
            aria-pressed={props.value === value}
            onClick={() => props.onChange(value)}
          >
            {name}
          </button>
        ))}
      </fieldset>
    </div>
  );
}
