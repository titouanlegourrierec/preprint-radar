import type { RankingMetric } from "../rankings";
import type { RankKind } from "../url-state";
import type { CountryMetric } from "../world";
import { Segmented } from "./Segmented";

/** What Rankings ranks, as its control and its table's caption name it. */
export const KIND_NAMES: Record<RankKind, string> = {
  institution: "Institutions",
  author: "Authors",
  country: "Countries",
};

/**
 * Recent papers are rarely cited yet: they rank by papers unless asked otherwise. Only
 * countries rank by people or impact.
 */
export function metricOf(metric: CountryMetric | null, archived: boolean): RankingMetric {
  return metric === "papers" || metric === "citations" ? metric : archived ? "citations" : "papers";
}

/** The countries' metric (UX-41): impact only for highly cited papers, which have citations. */
export function countryMetricOf(metric: CountryMetric | null, archived: boolean): CountryMetric {
  return metric === null || (metric === "impact" && !archived)
    ? metricOf(metric, archived)
    : metric;
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
