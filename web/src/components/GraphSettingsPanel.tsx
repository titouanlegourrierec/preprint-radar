import type { RefObject } from "preact";
import { useState } from "preact/hooks";
import type { YearRange } from "../archive-years";
import { countOf, formatShortDay } from "../format";
import { type GraphNode, matchStatus } from "../graph";
import type { Period } from "../period";
import { authorLayer, type GraphSettings } from "../preferences";
import type { FacetCount } from "../search";
import type { ArchiveSummary, DaySummary } from "../types";
import { ArchiveSourceSelect } from "./ArchiveYears";
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
  /** The first matches of the Highlight field, listed under it. */
  matches: GraphNode[];
  /** How many nodes match in all. */
  matchCount: number;
  /** The match shown last, `null` before one is, and its name. */
  matchIndex: number | null;
  matchLabel: string | null;
  /** Show the next match (1) or the previous one (-1). */
  onCycleMatch: (step: 1 | -1) => void;
  /** Show the match at this index of `matches`, and move the focus to its details. */
  onChooseMatch: (index: number) => void;
  categories: string[];
  category: string;
  onCategory: (category: string) => void;
  /** Days available in the store, with paper counts. */
  storeDays: DaySummary[];
  period: Period;
  onPeriod: (period: Period) => void;
  archiveYears: ArchiveSummary[];
  /** The archive's years shown, `null` for the recent days. */
  archiveRange: YearRange | null;
  onArchiveRange: (range: YearRange | null) => void;
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
  /** Save the graph as drawn, or its nodes and links for Gephi (§17.1 #8). */
  onExportPng: () => void;
  onExportGraphML: () => void;
  onFit: () => void;
  onReset: () => void;
  /** Whether any shown node has citations (sizing by citations then shows something). */
  cited: boolean;
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
  // The listed match the arrow keys point at, and whether the list shows (field focused).
  const [active, setActive] = useState<number | null>(null);
  const [listing, setListing] = useState(false);
  const listed = listing && props.highlight.trim() !== "" && props.matches.length > 0;
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
          <div class="graph-settings__find">
            <input
              ref={props.highlightInput}
              type="search"
              role="combobox"
              placeholder="Highlight nodes…  ( / )"
              aria-label="Highlight nodes by name"
              aria-autocomplete="list"
              aria-expanded={listed}
              aria-controls="graph-matches"
              aria-activedescendant={
                listed && active !== null ? `graph-match-${active}` : undefined
              }
              value={props.highlight}
              onInput={(event) => {
                setActive(null);
                props.onHighlight(event.currentTarget.value);
              }}
              onFocus={() => setListing(true)}
              onBlur={() => {
                setListing(false);
                setActive(null);
              }}
              onKeyDown={(event) => {
                const last = props.matches.length - 1;
                if (event.key === "ArrowDown" && listed) {
                  event.preventDefault();
                  setActive(active === null || active >= last ? 0 : active + 1);
                } else if (event.key === "ArrowUp" && listed) {
                  event.preventDefault();
                  setActive(active === null || active <= 0 ? last : active - 1);
                } else if (event.key === "Enter" && active !== null && listed) {
                  event.preventDefault();
                  props.onChooseMatch(active);
                } else if (event.key === "Enter") {
                  event.preventDefault();
                  props.onCycleMatch(event.shiftKey ? -1 : 1);
                }
              }}
            />
            {listed && (
              <div
                id="graph-matches"
                class="graph-settings__matches"
                role="listbox"
                aria-label="Matches"
              >
                {props.matches.map((node, index) => (
                  <div
                    key={node.id}
                    id={`graph-match-${index}`}
                    role="option"
                    tabIndex={-1}
                    aria-selected={index === active}
                    class={index === active ? "is-active" : undefined}
                    // Chosen before the field loses the focus, which would close the list.
                    onMouseDown={(event) => {
                      event.preventDefault();
                      props.onChooseMatch(index);
                    }}
                  >
                    <i class={`graph__dot graph__dot--${node.kind}`} aria-hidden="true" />
                    {node.label}
                  </div>
                ))}
              </div>
            )}
          </div>
          {props.highlight.trim() !== "" && (
            <p class="graph-settings__note" role="status">
              {matchStatus(props.matchCount, props.matchIndex, props.matchLabel)}
            </p>
          )}

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
            {props.archiveYears.length > 0 && (
              <ArchiveSourceSelect
                class="ctl-select"
                years={props.archiveYears}
                range={props.archiveRange}
                onChange={props.onArchiveRange}
              />
            )}
            {props.archiveRange === null && (
              <PeriodPicker
                days={props.storeDays}
                period={props.period}
                onChange={props.onPeriod}
              />
            )}
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
              {props.query.trim() ? `${countOf(props.paperCount, "matching paper")}, ` : ""}
              {props.affiliatedCount.toLocaleString()} with affiliations
            </p>
          </fieldset>

          <fieldset>
            <legend>Show</legend>
            <Checkbox
              label="Papers"
              checked={settings.papers}
              onChange={(papers) => onSettings({ papers })}
            />
            <Checkbox
              label="Institutions"
              checked={settings.institutions}
              onChange={(institutions) => onSettings({ institutions })}
            />
            <Checkbox
              label="Authors"
              checked={settings.authors}
              onChange={(authors) => onSettings(authorLayer(settings, authors))}
            />
            <Checkbox
              label="Isolated nodes"
              checked={settings.isolated}
              onChange={(isolated) => onSettings({ isolated })}
            />
            <p class="graph-settings__note">
              {settings.papers
                ? "Papers link to their authors, and institutions to their authors (or to the paper)."
                : "Without papers, nodes are linked when they share a paper."}
            </p>
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
            {settings.authors && settings.minAuthorPapers > 1 && (
              <p class="graph-settings__note">
                Authors of fewer papers are hidden: at 1, the graph is about three times larger and
                slower to settle.
              </p>
            )}
            <label class="ctl-select">
              <span>Top institutions &amp; authors</span>
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
            <label class="ctl-select">
              <span>Size by</span>
              <select
                value={settings.sizeBy}
                onChange={(event) =>
                  onSettings({
                    sizeBy: event.currentTarget.value === "citations" ? "citations" : "papers",
                  })
                }
              >
                <option value="papers">Papers</option>
                <option value="citations">Citations</option>
              </select>
            </label>
            {settings.sizeBy === "citations" && !props.cited && (
              <p class="graph-settings__note">
                No citations yet for these papers: recent papers are rarely cited, and new ones get
                their counts within days. The highly cited papers (From) show them best.
              </p>
            )}
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
          <div class="graph-settings__buttons">
            <button
              type="button"
              title="Save the graph as drawn, for slides"
              onClick={props.onExportPng}
            >
              PNG
            </button>
            <button
              type="button"
              title="Save its nodes and links, for Gephi, Cytoscape or NetworkX"
              onClick={props.onExportGraphML}
            >
              GraphML
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
