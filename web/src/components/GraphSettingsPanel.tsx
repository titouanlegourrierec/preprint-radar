import type { RefObject } from "preact";
import { formatShortDay } from "../format";
import type { Period } from "../period";
import type { GraphSettings } from "../preferences";
import type { FacetCount } from "../search";
import type { DaySummary } from "../types";
import { PeriodPicker } from "./PeriodPicker";
import { VenueSelect } from "./VenueSelect";

const MAX_NODES_OPTIONS = [0, 100, 300, 1000, 3000];

type NumericSetting = {
  [K in keyof GraphSettings]: GraphSettings[K] extends number ? K : never;
}[keyof GraphSettings];

const FORCE_SLIDERS: readonly {
  key: NumericSetting;
  label: string;
  min: number;
  max: number;
  step: number;
}[] = [
  { key: "centerForce", label: "Center force", min: 0, max: 1, step: 0.01 },
  { key: "repelForce", label: "Repel force", min: 0, max: 40, step: 0.5 },
  { key: "linkForce", label: "Link force", min: 0, max: 2, step: 0.05 },
  { key: "linkDistance", label: "Link distance", min: 10, max: 300, step: 5 },
  { key: "nodeSize", label: "Node size", min: 0.4, max: 2.5, step: 0.05 },
  { key: "labelThreshold", label: "Label threshold", min: 0.1, max: 3, step: 0.05 },
];

interface Props {
  open: boolean;
  onToggle: () => void;
  highlight: string;
  highlightInput: RefObject<HTMLInputElement>;
  onHighlight: (text: string) => void;
  onHighlightSubmit: () => void;
  categories: string[];
  category: string;
  onCategory: (category: string) => void;
  /** Days available in the store, with paper counts. */
  storeDays: DaySummary[];
  period: Period;
  onPeriod: (period: Period) => void;
  query: string;
  onQuery: (query: string) => void;
  venues: FacetCount[];
  venue: string | null;
  onVenue: (venue: string | null) => void;
  paperCount: number;
  affiliatedCount: number;
  settings: GraphSettings;
  onSettings: (patch: Partial<GraphSettings>) => void;
  days: string[];
  /** Index of the last day shown by the time-lapse, `null` for all days. */
  cutoff: number | null;
  onCutoff: (cutoff: number | null) => void;
  playing: boolean;
  onReplay: () => void;
  onReheat: () => void;
  onFit: () => void;
  onReset: () => void;
}

function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  output?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label class="ctl">
      <span>{props.label}</span>
      <output>{props.output ?? props.value}</output>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        disabled={props.disabled}
        onInput={(event) => props.onChange(Number(event.currentTarget.value))}
      />
    </label>
  );
}

function Checkbox(props: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label class="ctl-row">
      <input
        type="checkbox"
        checked={props.checked}
        onChange={(event) => props.onChange(event.currentTarget.checked)}
      />
      {props.label}
    </label>
  );
}

/** Floating, collapsible settings of the graph view. */
export function GraphSettingsPanel(props: Props) {
  const { settings, onSettings, days, cutoff } = props;
  const lastIndex = Math.max(0, days.length - 1);
  const cutoffDay = cutoff === null ? undefined : days[cutoff];

  return (
    <section class="graph-settings" aria-label="Graph settings">
      <button
        type="button"
        class="graph-settings__head"
        aria-expanded={props.open}
        onClick={props.onToggle}
      >
        <span>Graph settings</span>
        <span aria-hidden="true">{props.open ? "▾" : "▸"}</span>
      </button>

      {props.open && (
        <div class="graph-settings__body">
          <input
            ref={props.highlightInput}
            type="search"
            placeholder="Highlight nodes…  ( / )"
            aria-label="Highlight nodes by name"
            value={props.highlight}
            onInput={(event) => props.onHighlight(event.currentTarget.value)}
            onKeyDown={(event) => event.key === "Enter" && props.onHighlightSubmit()}
          />

          <fieldset>
            <legend>Papers</legend>
            {props.categories.length > 1 && (
              <label class="ctl-select">
                <span>Category</span>
                <select
                  value={props.category}
                  onChange={(event) => props.onCategory(event.currentTarget.value)}
                >
                  {props.categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <PeriodPicker days={props.storeDays} period={props.period} onChange={props.onPeriod} />
            <div class="ctl-select">
              <span aria-hidden="true">Venue</span>
              <VenueSelect venues={props.venues} value={props.venue} onChange={props.onVenue} />
            </div>
            <input
              type="search"
              placeholder="Only papers matching…"
              aria-label="Only include papers matching these words"
              value={props.query}
              onInput={(event) => props.onQuery(event.currentTarget.value)}
            />
            <p class="graph-settings__note">
              {props.query.trim() ? `${props.paperCount.toLocaleString()} matching papers, ` : ""}
              {props.affiliatedCount.toLocaleString()} with affiliations
            </p>
          </fieldset>

          <fieldset>
            <legend>Show</legend>
            <Checkbox
              label="Institutions"
              checked={settings.institutions}
              onChange={(institutions) => onSettings({ institutions })}
            />
            <Checkbox
              label="Authors"
              checked={settings.authors}
              onChange={(authors) => onSettings({ authors })}
            />
            <Checkbox
              label="Isolated nodes"
              checked={settings.isolated}
              onChange={(isolated) => onSettings({ isolated })}
            />
            <Slider
              label="Institution ≥ papers"
              value={settings.minInstitutionPapers}
              min={1}
              max={10}
              step={1}
              onChange={(minInstitutionPapers) => onSettings({ minInstitutionPapers })}
            />
            <Slider
              label="Author ≥ papers"
              value={settings.minAuthorPapers}
              min={1}
              max={10}
              step={1}
              onChange={(minAuthorPapers) => onSettings({ minAuthorPapers })}
            />
            <label class="ctl-select">
              <span>Max nodes</span>
              <select
                value={settings.maxNodes}
                onChange={(event) => onSettings({ maxNodes: Number(event.currentTarget.value) })}
              >
                {MAX_NODES_OPTIONS.map((count) => (
                  <option key={count} value={count}>
                    {count === 0 ? "All" : `Top ${count.toLocaleString()}`}
                  </option>
                ))}
              </select>
            </label>
          </fieldset>

          <fieldset>
            <legend>Forces &amp; display</legend>
            {FORCE_SLIDERS.map(({ key, label, min, max, step }) => (
              <Slider
                key={key}
                label={label}
                value={settings[key]}
                min={min}
                max={max}
                step={step}
                onChange={(value) => onSettings({ [key]: value })}
              />
            ))}
          </fieldset>

          <fieldset>
            <legend>Time-lapse</legend>
            <Slider
              label="Announced up to"
              value={cutoff ?? lastIndex}
              min={0}
              max={lastIndex}
              step={1}
              output={cutoffDay === undefined ? "all" : formatShortDay(cutoffDay)}
              disabled={days.length < 2}
              onChange={(index) => props.onCutoff(index >= lastIndex ? null : index)}
            />
            <div class="graph-settings__buttons">
              <button type="button" disabled={days.length < 2} onClick={props.onReplay}>
                {props.playing ? "■ Stop" : "▶ Replay growth"}
              </button>
            </div>
          </fieldset>

          <div class="graph-settings__buttons">
            <button type="button" title="Shake the layout" onClick={props.onReheat}>
              Reheat
            </button>
            <button type="button" title="Fit graph to view" onClick={props.onFit}>
              Fit
            </button>
            <button type="button" title="Back to default settings" onClick={props.onReset}>
              Reset
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
