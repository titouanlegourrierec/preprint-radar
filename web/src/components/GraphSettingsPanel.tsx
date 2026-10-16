import { authorLayer, type GraphSettings } from "../preferences";
import { ChevronIcon, DownloadIcon, SelectChevron } from "./icons";
import { Segmented } from "./Segmented";

const MAX_NODES_OPTIONS = [0, 100, 300, 1000, 3000];
/** The thresholds of the institution and author layers: at least 1 to 10 papers. */
const MIN_PAPERS_OPTIONS = Array.from({ length: 10 }, (_, index) => index + 1);

type NumericSetting = {
  [K in keyof GraphSettings]: GraphSettings[K] extends number ? K : never;
}[keyof GraphSettings];

/** The forces of the layout, folded under Layout: few readers need them (UX-29). */
const FORCE_SLIDERS: readonly {
  key: NumericSetting;
  label: string;
  min: number;
  max: number;
  step: number;
}[] = [
  { key: "centerForce", label: "Pull to the center", min: 0, max: 1, step: 0.01 },
  { key: "repelForce", label: "Repulsion", min: 0, max: 40, step: 0.5 },
  { key: "linkForce", label: "Link strength", min: 0, max: 2, step: 0.05 },
  { key: "linkDistance", label: "Link length", min: 10, max: 300, step: 5 },
];

/**
 * The Labels slider reads the other way from `labelThreshold`, the radius past which a node
 * is labelled: to the right, a lower threshold and more labels.
 */
const LABELS = { min: 0.1, max: 3 } as const;

function labelsValue(threshold: number): number {
  return Math.round((LABELS.min + LABELS.max - threshold) * 100) / 100;
}

interface Props {
  open: boolean;
  onToggle: () => void;
  settings: GraphSettings;
  onSettings: (patch: Partial<GraphSettings>) => void;
  onReheat: () => void;
  /** Save the graph as drawn, or its nodes and links for Gephi (§17.1 #8). */
  onExportPng: () => void;
  onExportGraphML: () => void;
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
  /** The value as shown; none for a slider whose ends say enough. */
  output?: string | null;
  onChange: (value: number) => void;
}) {
  return (
    <label class="ctl">
      <span>{props.label}</span>
      {props.output !== null && <output>{props.output ?? props.value}</output>}
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onInput={(event) => props.onChange(Number(event.currentTarget.value))}
      />
    </label>
  );
}

/** A layer of nodes: its checkbox, named with the legend's color, and its threshold. */
function Layer(props: {
  kind: "paper" | "institution" | "author";
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** At least how many papers a node of the layer has, with its setter; none for papers. */
  min?: { value: number; label: string; onChange: (value: number) => void };
}) {
  return (
    <div class="graph-layer">
      <label class="ctl-row">
        <input
          type="checkbox"
          checked={props.checked}
          onChange={(event) => props.onChange(event.currentTarget.checked)}
        />
        <i class={`graph__dot graph__dot--${props.kind}`} aria-hidden="true" />
        {props.label}
      </label>
      {props.min && (
        <span class="graph-settings__select graph-layer__min">
          <select
            aria-label={props.min.label}
            value={props.min.value}
            onChange={(event) => props.min?.onChange(Number(event.currentTarget.value))}
          >
            {MIN_PAPERS_OPTIONS.map((count) => (
              <option key={count} value={count}>
                {count === 1 ? "≥ 1 paper" : `≥ ${count} papers`}
              </option>
            ))}
          </select>
          <SelectChevron />
        </span>
      )}
    </div>
  );
}

/**
 * Floating, collapsible settings of the graph view: what it draws and how (UX-29). The
 * papers it draws are chosen with the Papers button at the top left (`GraphFilters`), and
 * its nodes found with the field under that button (`GraphFind`).
 */
export function GraphSettingsPanel(props: Props) {
  const { settings, onSettings } = props;

  return (
    <section
      class={props.open ? "graph-settings graph-settings--open" : "graph-settings"}
      aria-label="Graph settings"
    >
      <div class="graph-settings__head">
        <button
          type="button"
          class="graph-settings__toggle"
          aria-expanded={props.open}
          onClick={props.onToggle}
        >
          <span>Graph settings</span>
          <ChevronIcon up={props.open} />
        </button>
        {props.open && (
          <button
            type="button"
            class="graph-settings__reset"
            title="Restore the default settings"
            onClick={props.onReset}
          >
            Reset
          </button>
        )}
      </div>

      {props.open && (
        <div class="graph-settings__body">
          <fieldset>
            <legend>Nodes</legend>
            <Layer
              kind="paper"
              label="Papers"
              checked={settings.papers}
              onChange={(papers) => onSettings({ papers })}
            />
            <Layer
              kind="institution"
              label="Institutions"
              checked={settings.institutions}
              onChange={(institutions) => onSettings({ institutions })}
              min={{
                value: settings.minInstitutionPapers,
                label: "Institutions of at least",
                onChange: (minInstitutionPapers) => onSettings({ minInstitutionPapers }),
              }}
            />
            <Layer
              kind="author"
              label="Authors"
              checked={settings.authors}
              onChange={(authors) => onSettings(authorLayer(settings, authors))}
              min={{
                value: settings.minAuthorPapers,
                label: "Authors of at least",
                onChange: (minAuthorPapers) => onSettings({ minAuthorPapers }),
              }}
            />
            <label class="ctl-row">
              <input
                type="checkbox"
                checked={settings.isolated}
                onChange={(event) => onSettings({ isolated: event.currentTarget.checked })}
              />
              Isolated nodes
            </label>
            {!settings.papers && (
              <p class="graph-settings__note">
                Without papers, nodes are linked when they share a paper.
              </p>
            )}
            <label class="ctl-select" title="Only the institutions and authors of most papers">
              <span>Limit</span>
              <span class="graph-settings__select">
                <select
                  value={settings.maxNodes}
                  onChange={(event) => onSettings({ maxNodes: Number(event.currentTarget.value) })}
                >
                  {MAX_NODES_OPTIONS.map((count) => (
                    <option key={count} value={count}>
                      {count === 0 ? "None" : `Top ${count.toLocaleString()}`}
                    </option>
                  ))}
                </select>
                <SelectChevron />
              </span>
            </label>
          </fieldset>

          <fieldset>
            <legend>Appearance</legend>
            <div class="ctl-select">
              <span aria-hidden="true">Size by</span>
              <Segmented
                legend="Size by"
                class="graph-settings__segmented"
                options={[
                  ["papers", "Papers"],
                  ["citations", "Citations"],
                ]}
                value={settings.sizeBy}
                onChange={(sizeBy) => onSettings({ sizeBy })}
              />
            </div>
            {settings.sizeBy === "citations" && !props.cited && (
              <p class="graph-settings__note">
                No citations yet for these papers: recent papers are rarely cited, and new ones get
                their counts within days. The highly cited papers (the chip above) show them best.
              </p>
            )}
            <Slider
              label="Node size"
              value={settings.nodeSize}
              min={0.4}
              max={2.5}
              step={0.05}
              output={`${settings.nodeSize.toFixed(2)}×`}
              onChange={(nodeSize) => onSettings({ nodeSize })}
            />
            <Slider
              label="Labels"
              value={labelsValue(settings.labelThreshold)}
              min={LABELS.min}
              max={LABELS.max}
              step={0.05}
              output={null}
              onChange={(value) => onSettings({ labelThreshold: labelsValue(value) })}
            />
          </fieldset>

          <details class="graph-settings__layout">
            <summary class="graph-settings__summary">Layout</summary>
            <div class="graph-settings__forces">
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
              <button
                type="button"
                class="graph-settings__button"
                title="Shake the layout, which then settles again"
                onClick={props.onReheat}
              >
                Reheat
              </button>
            </div>
          </details>

          <div class="graph-settings__export">
            <span>Export</span>
            <button
              type="button"
              class="graph-settings__button"
              title="Save the graph as drawn, for slides"
              onClick={props.onExportPng}
            >
              <DownloadIcon />
              PNG
            </button>
            <button
              type="button"
              class="graph-settings__button"
              title="Save its nodes and links, for Gephi, Cytoscape or NetworkX"
              onClick={props.onExportGraphML}
            >
              <DownloadIcon />
              GraphML
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
