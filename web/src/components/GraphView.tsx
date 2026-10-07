import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { YearRange } from "../archive-years";
import { download, downloadBlob } from "../download";
import { countOf } from "../format";
import {
  buildGraph,
  canonicalNodeId,
  type EntityKind,
  entitiesByPaper,
  type GraphOptions,
  isEntity,
  nodeConnections,
  nodeLabel,
  nodeMatches,
  papersOfNode,
  replaySteps,
} from "../graph";
import { exportName, toGraphML } from "../graph-export";
import { GraphRenderer } from "../graph-renderer";
import { useMediaQuery } from "../hooks/use-media-query";
import { isTyping } from "../keyboard";
import type { Period } from "../period";
import {
  DEFAULT_GRAPH_SETTINGS,
  type GraphSettings,
  loadGraphIntroRead,
  loadGraphSettings,
  saveGraphIntroRead,
  saveGraphSettings,
} from "../preferences";
import type { FacetCount } from "../search";
import { searchKey } from "../text";
import type { ArchiveSummary, DaySummary, Paper } from "../types";
import { GraphDetails } from "./GraphDetails";
import { GraphLegend } from "./GraphLegend";
import { GraphSettingsPanel } from "./GraphSettingsPanel";

const DETAILS_CONNECTIONS = 8;
/** Space taken by the overlays (width + margins), kept free when fitting or selecting. */
const DETAILS_WIDTH_PX = 344;
const SETTINGS_WIDTH_PX = 274;
const WIDE_SCREEN = "(min-width: 900px)";
const REPLAY_STEP_MS = 900;
/** Zoom of one press of the + or − button. */
const ZOOM_STEP = 1.5;
/** Matches listed under the Highlight field. */
const LISTED_MATCHES = 10;

interface Props {
  /** Papers the graph is built from. */
  papers: Paper[];
  /** Why there is nothing to show yet, if so. */
  notice: string | null;
  categories: string[];
  category: string;
  onCategory: (category: string) => void;
  /** Days available in the store, with paper counts. */
  storeDays: DaySummary[];
  period: Period;
  onPeriod: (period: Period) => void;
  /** Years of the archive of highly cited papers. */
  archiveYears: ArchiveSummary[];
  /** The archive's years shown, `null` for the recent days. */
  archiveRange: YearRange | null;
  onArchiveRange: (range: YearRange | null) => void;
  query: string;
  onQuery: (query: string) => void;
  venues: FacetCount[];
  venue: string | null;
  onVenue: (venue: string | null) => void;
  onShowPapers: (kind: EntityKind, label: string) => void;
  /** Show one paper in the list, expanded (its permalink). */
  onOpenPaper: (paper: Paper) => void;
  /** Paper to select and center on (from the list or a shared link), by arXiv id. */
  focusPaper: string | null;
  /** The focused paper is no longer selected. */
  onFocusPaperLeft: () => void;
  /** Scheme shown right now; the canvas re-reads its colors when it changes. */
  theme: "light" | "dark";
  /** Citation count of each paper, by arXiv id, when known. */
  citations: ReadonlyMap<string, number>;
  /** The node focused on: the graph of its papers alone (§17.1 #8), `null` for all. */
  focus: string | null;
  onFocus: (id: string | null) => void;
}

/** Full-screen co-occurrence graph of the institutions and authors of the loaded papers. */
export function GraphView(props: Props) {
  const { papers, onShowPapers, onOpenPaper, theme, citations, onFocus } = props;
  // The node focused on, as the graph keys it: a link may write it otherwise.
  const focus = props.focus === null ? null : canonicalNodeId(props.focus);
  const [settings, setSettings] = useState<GraphSettings>(loadGraphSettings);
  const [panelOpen, setPanelOpen] = useState(() => window.matchMedia(WIDE_SCREEN).matches);
  const [highlight, setHighlight] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cutoff, setCutoff] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [introRead, setIntroRead] = useState(loadGraphIntroRead);

  const changeSettings = (patch: Partial<GraphSettings>) =>
    setSettings((current) => {
      const next = { ...current, ...patch };
      saveGraphSettings(next);
      return next;
    });

  // "Focus on this": the papers of one node alone, its ego network (§17.1 #8).
  const focusedPapers = useMemo(
    () => (focus ? papersOfNode(papers, focus) : papers),
    [papers, focus],
  );
  // Time-lapse: the announcement days of the papers (weeks or months for many), and the
  // last one shown.
  const days = useMemo(
    () => replaySteps([...new Set(focusedPapers.map((paper) => paper.announced))].sort()),
    [focusedPapers],
  );
  // A new set of papers starts over with every day shown.
  useEffect(() => {
    setCutoff(null);
    setPlaying(false);
  }, [days]);
  const lastDay = cutoff === null ? undefined : days[cutoff];
  const shownPapers = useMemo(
    () =>
      lastDay === undefined
        ? focusedPapers
        : focusedPapers.filter((paper) => paper.announced <= lastDay),
    [focusedPapers, lastDay],
  );
  useEffect(() => {
    if (!playing) return;
    const timer = setTimeout(() => {
      const next = (cutoff ?? -1) + 1;
      if (next >= days.length - 1) {
        setCutoff(null);
        setPlaying(false);
      } else {
        setCutoff(next);
      }
    }, REPLAY_STEP_MS);
    return () => clearTimeout(timer);
  }, [playing, cutoff, days.length]);

  const graphOptions: GraphOptions = useMemo(
    () => ({
      papers: settings.papers,
      institutions: settings.institutions,
      authors: settings.authors,
      isolated: settings.isolated,
      minPapers: { institution: settings.minInstitutionPapers, author: settings.minAuthorPapers },
      maxNodes: settings.maxNodes > 0 ? settings.maxNodes : Number.POSITIVE_INFINITY,
      citations,
    }),
    [
      citations,
      settings.papers,
      settings.institutions,
      settings.authors,
      settings.isolated,
      settings.minInstitutionPapers,
      settings.minAuthorPapers,
      settings.maxNodes,
    ],
  );
  const graph = useMemo(() => buildGraph(shownPapers, graphOptions), [shownPapers, graphOptions]);
  const nodesById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph]);
  const papersById = useMemo(
    () => new Map(shownPapers.map((paper) => [paper.arxiv_id, paper])),
    [shownPapers],
  );
  const affiliatedCount = useMemo(
    () => shownPapers.filter((paper) => (paper.affiliations ?? []).length > 0).length,
    [shownPapers],
  );
  const counts = useMemo(() => {
    const byKind = { paper: 0, institution: 0, author: 0 };
    for (const node of graph.nodes) byKind[node.kind]++;
    return byKind;
  }, [graph]);

  const highlightKey = searchKey(highlight);
  const highlighted = useMemo(
    () =>
      highlightKey
        ? new Set(graph.nodes.filter((node) => nodeMatches(node, highlightKey)).map((n) => n.id))
        : null,
    [graph, highlightKey],
  );
  const matches = useMemo(
    () => (highlighted ? graph.nodes.filter((node) => highlighted.has(node.id)) : []),
    [graph, highlighted],
  );
  // The match shown by Enter or the list, `null` until one is; new matches start over.
  const [matchIndex, setMatchIndex] = useState<number | null>(null);
  useEffect(() => setMatchIndex(null), [matches]);
  const selected = (selectedId && nodesById.get(selectedId)) || null;
  // The selected entity's most connected nodes (`nodeConnections`), from the institutions
  // and authors of each paper when papers are nodes themselves.
  const entities = useMemo(
    () => (settings.papers ? entitiesByPaper(graph) : null),
    [graph, settings.papers],
  );
  const connections = useMemo(
    () =>
      selected && isEntity(selected)
        ? nodeConnections(graph, selected, entities, DETAILS_CONNECTIONS)
        : [],
    [graph, selected, entities],
  );
  // A paper can be selected without being a node (no institution or author to link it to).
  const selectedPaper = selectedId?.startsWith("paper:")
    ? papersById.get(selectedId.slice("paper:".length))
    : undefined;

  // The renderer is imperative: create it once, then push every change to it.
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const highlightInput = useRef<HTMLInputElement>(null);
  const detailsRef = useRef<HTMLElement>(null);
  // Once the details of a match chosen from the list are shown, they take the focus.
  const [focusDetails, setFocusDetails] = useState(false);
  useEffect(() => {
    if (focusDetails && detailsRef.current) {
      detailsRef.current.focus();
      setFocusDetails(false);
    }
  });
  const rendererRef = useRef<GraphRenderer | null>(null);
  const openRef = useRef<(id: string) => void>(() => {});
  openRef.current = (id) => {
    const node = nodesById.get(id);
    if (node?.kind === "paper") {
      const paper = papersById.get(node.paperIds[0] ?? "");
      if (paper) onOpenPaper(paper);
    } else if (node) {
      onShowPapers(node.kind, node.label);
    }
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new GraphRenderer(
      canvas,
      { onSelect: setSelectedId, onOpen: (id) => openRef.current(id) },
      DEFAULT_GRAPH_SETTINGS,
    );
    rendererRef.current = renderer;
    return () => {
      renderer.destroy();
      rendererRef.current = null;
    };
  }, []);

  const { centerForce, repelForce, linkForce, linkDistance, nodeSize, sizeBy, labelThreshold } =
    settings;
  useEffect(() => {
    rendererRef.current?.setSettings({
      centerForce,
      repelForce,
      linkForce,
      linkDistance,
      nodeSize,
      sizeBy,
      labelThreshold,
    });
  }, [centerForce, repelForce, linkForce, linkDistance, nodeSize, sizeBy, labelThreshold]);
  useEffect(() => rendererRef.current?.refreshTheme(), [theme]);
  useEffect(() => rendererRef.current?.setGraph(graph), [graph]);
  // Select the focused paper once its papers are loaded, after the renderer has its node;
  // selecting something else afterwards lets the focus go.
  const { focusPaper, onFocusPaperLeft } = props;
  const focused = useRef<string | null>(null);
  const focusShown = useRef(false);
  useEffect(() => {
    if (!focusPaper) {
      focused.current = null;
      return;
    }
    if (focused.current === focusPaper || !papersById.has(focusPaper)) return;
    focused.current = focusPaper;
    const id = `paper:${focusPaper}`;
    setSelectedId(id);
    if (nodesById.has(id)) rendererRef.current?.focus(id);
  }, [focusPaper, papersById, nodesById]);
  useEffect(() => {
    if (!focusPaper) {
      focusShown.current = false;
    } else if (selectedId === `paper:${focusPaper}`) {
      focusShown.current = true;
    } else if (focusShown.current) {
      focusShown.current = false;
      onFocusPaperLeft();
    }
  }, [focusPaper, selectedId, onFocusPaperLeft]);
  useEffect(() => rendererRef.current?.setHighlight(highlighted), [highlighted]);
  useEffect(() => rendererRef.current?.setSelected(selected?.id ?? null), [selected]);
  useEffect(() => {
    const wide = window.matchMedia(WIDE_SCREEN).matches;
    rendererRef.current?.setOverlays({
      left: wide ? DETAILS_WIDTH_PX : 0,
      right: panelOpen && wide ? SETTINGS_WIDTH_PX : 0,
    });
  }, [panelOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedId(null);
      } else if (event.key === "/" && !isTyping(event.target)) {
        event.preventDefault();
        setPanelOpen(true);
        requestAnimationFrame(() => highlightInput.current?.focus());
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  /** Select a match and center on it; a match chosen in the list takes the focus there. */
  const showMatch = (index: number, moveFocus: boolean) => {
    const match = matches[index];
    if (!match) return;
    setMatchIndex(index);
    setSelectedId(match.id);
    rendererRef.current?.focus(match.id);
    if (moveFocus) setFocusDetails(true);
  };
  /** The next (or previous) match, from the first (or last) one, round and round. */
  const cycleMatch = (step: 1 | -1) => {
    if (matches.length === 0) return;
    const start = step === 1 ? -1 : matches.length;
    showMatch(
      ((((matchIndex ?? start) + step) % matches.length) + matches.length) % matches.length,
      false,
    );
  };
  const coarse = useMediaQuery("(pointer: coarse)");
  const selectNode = (id: string) => {
    setSelectedId(id);
    rendererRef.current?.focus(id);
  };

  const kinds = [settings.institutions && "institutions", settings.authors && "authors"].filter(
    Boolean,
  );
  const selectedEntity = selected && isEntity(selected) ? selected : null;
  // Its name: the node's, else its usual spelling among the papers, else its key.
  const undrawnLabel = useMemo(
    () => (focus !== null && !nodesById.has(focus) ? nodeLabel(papers, focus) : null),
    [focus, nodesById, papers],
  );
  const focusLabel = focus
    ? (nodesById.get(focus)?.label ?? undrawnLabel ?? focus.slice(focus.indexOf(":") + 1))
    : null;
  // A focus kept from other papers (another period, year or venue) may have none here;
  // while papers load, or failed to, there are none to tell.
  const focusEmpty = focus !== null && props.notice === null && focusedPapers.length === 0;
  const fileName = exportName(new Date().toISOString().slice(0, 10), focus);
  const exportGraphML = () =>
    download(`${fileName}.graphml`, toGraphML(graph), "application/graphml+xml");
  const exportPng = async () => {
    const blob = await rendererRef.current?.toPng();
    if (blob) downloadBlob(`${fileName}.png`, blob);
  };
  const emptyMessage =
    props.notice ??
    (focusEmpty
      ? null
      : papers.length === 0
        ? "No paper matches these settings."
        : graph.nodes.length > 0
          ? null
          : kinds.length === 0
            ? "Turn on institutions or authors in the graph settings."
            : `No ${kinds.join(" or ")} to show: affiliations are known so far for ` +
              `${affiliatedCount.toLocaleString()} of ${countOf(shownPapers.length, "paper")}.`);

  return (
    <main class="graph" id="main">
      {!introRead && (
        <section class="graph__intro" aria-label="About the graph">
          <p>
            Papers (green squares) link to their institutions (orange) and, when shown, authors
            (blue). Drag to move, scroll or pinch to zoom, select a node for its details;
            double-click, or "Show papers" in the details, to list its papers. The settings choose
            what is shown.
          </p>
          <button
            type="button"
            class="button"
            onClick={() => {
              setIntroRead(true);
              saveGraphIntroRead();
            }}
          >
            Got it
          </button>
        </section>
      )}
      <canvas
        ref={canvasRef}
        class="graph__canvas"
        role="img"
        aria-label={`Graph of ${[
          countOf(counts.paper, "paper"),
          countOf(counts.institution, "institution"),
          countOf(counts.author, "author"),
          countOf(graph.links.length, "link"),
        ].join(", ")}`}
        aria-describedby="graph-equivalent"
      />
      <p id="graph-equivalent" class="visually-hidden">
        The Rankings tab lists the same institutions and authors in a table. The Highlight field of
        the settings finds a node by name, and Enter goes from one match to the next.
      </p>
      <fieldset class="graph__zoom">
        <legend class="visually-hidden">Zoom</legend>
        <button
          type="button"
          aria-label="Zoom in"
          title="Zoom in"
          onClick={() => rendererRef.current?.zoomBy(ZOOM_STEP)}
        >
          +
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          title="Zoom out"
          onClick={() => rendererRef.current?.zoomBy(1 / ZOOM_STEP)}
        >
          −
        </button>
        <button
          type="button"
          aria-label="Fit the graph to the view"
          title="Fit"
          onClick={() => rendererRef.current?.fit()}
        >
          ⤢
        </button>
      </fieldset>

      {emptyMessage && <p class="graph__empty">{emptyMessage}</p>}

      {focusLabel && (
        <p class="graph__focus" role="status">
          {props.notice !== null
            ? `Focused on ${focusLabel}.`
            : focusEmpty
              ? `${focusLabel} has no paper among these.`
              : `${focusLabel} and ${
                  focusedPapers.length === 1
                    ? "its paper"
                    : `its ${countOf(focusedPapers.length, "paper")}`
                }, with their institutions and authors.`}{" "}
          <button type="button" class="link-button" onClick={() => onFocus(null)}>
            Show everything
          </button>
        </p>
      )}

      {(selected || selectedPaper) && (
        <GraphDetails
          entity={selectedEntity}
          paper={selectedPaper}
          absent={
            selected
              ? null
              : !settings.papers
                ? "Papers are hidden: turn them on in the graph settings to see this one."
                : !selectedPaper?.affiliations?.length && !settings.authors
                  ? "No affiliations are known for this paper yet: turn on Authors to see it with its authors."
                  : "Not in the graph with these settings: its institutions and authors are filtered out."
          }
          connections={connections}
          papersById={papersById}
          options={graphOptions}
          citations={citations}
          focus={focus}
          detailsRef={detailsRef}
          onClose={() => setSelectedId(null)}
          onSelect={selectNode}
          onShowPapers={onShowPapers}
          onFocus={onFocus}
          onOpenPaper={onOpenPaper}
        />
      )}

      <GraphSettingsPanel
        open={panelOpen}
        onToggle={() => setPanelOpen(!panelOpen)}
        highlight={highlight}
        highlightInput={highlightInput}
        onHighlight={setHighlight}
        matches={matches.slice(0, LISTED_MATCHES)}
        matchCount={matches.length}
        matchIndex={matchIndex}
        matchLabel={matchIndex === null ? null : (matches[matchIndex]?.label ?? null)}
        onCycleMatch={cycleMatch}
        onChooseMatch={(index) => showMatch(index, true)}
        categories={props.categories}
        category={props.category}
        onCategory={props.onCategory}
        storeDays={props.storeDays}
        period={props.period}
        onPeriod={props.onPeriod}
        archiveYears={props.archiveYears}
        archiveRange={props.archiveRange}
        onArchiveRange={props.onArchiveRange}
        query={props.query}
        onQuery={props.onQuery}
        venues={props.venues}
        venue={props.venue}
        onVenue={props.onVenue}
        paperCount={shownPapers.length}
        affiliatedCount={affiliatedCount}
        settings={settings}
        onSettings={changeSettings}
        cited={graph.nodes.some((node) => node.citations > 0)}
        days={days}
        cutoff={cutoff}
        onCutoff={(value) => {
          setPlaying(false);
          setCutoff(value);
        }}
        playing={playing}
        onReplay={() => {
          setCutoff(playing ? null : 0);
          setPlaying(!playing);
        }}
        onReheat={() => rendererRef.current?.reheat()}
        onExportPng={exportPng}
        onExportGraphML={exportGraphML}
        onFit={() => rendererRef.current?.fit()}
        onReset={() => changeSettings(DEFAULT_GRAPH_SETTINGS)}
      />

      <GraphLegend graph={graph} counts={counts} cap={settings.maxNodes} />
      <p class="graph__hint">
        {coarse
          ? "drag · pinch to zoom · tap = details · double-tap = open in the list"
          : "drag · scroll to zoom · click = details · double-click = open in the list"}
      </p>
    </main>
  );
}
