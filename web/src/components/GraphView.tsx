import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { formatDay } from "../format";
import { buildGraph, type GraphNode, type NodeKind, nodeMatches, searchKey } from "../graph";
import { GraphRenderer } from "../graph-renderer";
import type { Period } from "../period";
import {
  DEFAULT_GRAPH_SETTINGS,
  type GraphSettings,
  loadGraphSettings,
  saveGraphSettings,
} from "../preferences";
import type { FacetCount } from "../search";
import type { DaySummary, Paper } from "../types";
import { GraphSettingsPanel } from "./GraphSettingsPanel";

const DETAILS_PAPERS = 8;
const DETAILS_CONNECTIONS = 8;
/** Space taken by the overlays (width + margins), kept free when fitting or selecting. */
const DETAILS_WIDTH_PX = 344;
const SETTINGS_WIDTH_PX = 274;
const WIDE_SCREEN = "(min-width: 900px)";
const REPLAY_STEP_MS = 900;

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
  query: string;
  onQuery: (query: string) => void;
  venues: FacetCount[];
  venue: string | null;
  onVenue: (venue: string | null) => void;
  onShowPapers: (kind: NodeKind, label: string) => void;
}

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLSelectElement ||
    target instanceof HTMLTextAreaElement
  );
}

/** Full-screen co-occurrence graph of the institutions and authors of the loaded papers. */
export function GraphView(props: Props) {
  const { papers, onShowPapers } = props;
  const [settings, setSettings] = useState<GraphSettings>(loadGraphSettings);
  const [panelOpen, setPanelOpen] = useState(() => window.matchMedia(WIDE_SCREEN).matches);
  const [highlight, setHighlight] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cutoff, setCutoff] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  const changeSettings = (patch: Partial<GraphSettings>) =>
    setSettings((current) => {
      const next = { ...current, ...patch };
      saveGraphSettings(next);
      return next;
    });

  // Time-lapse: the announcement days of the papers, and the last one shown.
  const days = useMemo(() => [...new Set(papers.map((paper) => paper.announced))].sort(), [papers]);
  // A new set of papers starts over with every day shown.
  useEffect(() => {
    setCutoff(null);
    setPlaying(false);
  }, [days]);
  const lastDay = cutoff === null ? undefined : days[cutoff];
  const shownPapers = useMemo(
    () => (lastDay === undefined ? papers : papers.filter((paper) => paper.announced <= lastDay)),
    [papers, lastDay],
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

  const graph = useMemo(
    () =>
      buildGraph(shownPapers, {
        institutions: settings.institutions,
        authors: settings.authors,
        isolated: settings.isolated,
        minPapers: { institution: settings.minInstitutionPapers, author: settings.minAuthorPapers },
        maxNodes: settings.maxNodes > 0 ? settings.maxNodes : Number.POSITIVE_INFINITY,
      }),
    [
      shownPapers,
      settings.institutions,
      settings.authors,
      settings.isolated,
      settings.minInstitutionPapers,
      settings.minAuthorPapers,
      settings.maxNodes,
    ],
  );
  const nodesById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph]);
  const papersById = useMemo(
    () => new Map(shownPapers.map((paper) => [paper.arxiv_id, paper])),
    [shownPapers],
  );
  const affiliatedCount = useMemo(
    () => shownPapers.filter((paper) => (paper.affiliations ?? []).length > 0).length,
    [shownPapers],
  );
  const institutionCount = useMemo(
    () => graph.nodes.filter((node) => node.kind === "institution").length,
    [graph],
  );

  const highlightKey = searchKey(highlight);
  const highlighted = useMemo(
    () =>
      highlightKey
        ? new Set(graph.nodes.filter((node) => nodeMatches(node, highlightKey)).map((n) => n.id))
        : null,
    [graph, highlightKey],
  );
  const selected = (selectedId && nodesById.get(selectedId)) || null;
  const connections = useMemo(() => {
    if (!selected) return [];
    return graph.links
      .filter((link) => link.source === selected.id || link.target === selected.id)
      .map((link) => ({
        node: nodesById.get(link.source === selected.id ? link.target : link.source),
        weight: link.weight,
      }))
      .filter((entry): entry is { node: GraphNode; weight: number } => entry.node !== undefined)
      .sort((a, b) => b.weight - a.weight || b.node.paperIds.length - a.node.paperIds.length)
      .slice(0, DETAILS_CONNECTIONS);
  }, [graph, nodesById, selected]);

  // The renderer is imperative: create it once, then push every change to it.
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const highlightInput = useRef<HTMLInputElement>(null);
  const rendererRef = useRef<GraphRenderer | null>(null);
  const openRef = useRef<(id: string) => void>(() => {});
  openRef.current = (id) => {
    const node = nodesById.get(id);
    if (node) onShowPapers(node.kind, node.label);
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

  const { centerForce, repelForce, linkForce, linkDistance, nodeSize, labelThreshold } = settings;
  useEffect(() => {
    rendererRef.current?.setSettings({
      centerForce,
      repelForce,
      linkForce,
      linkDistance,
      nodeSize,
      labelThreshold,
    });
  }, [centerForce, repelForce, linkForce, linkDistance, nodeSize, labelThreshold]);
  useEffect(() => rendererRef.current?.setGraph(graph), [graph]);
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

  const focusFirstMatch = () => {
    const match = graph.nodes.find((node) => highlighted?.has(node.id));
    if (match) {
      setSelectedId(match.id);
      rendererRef.current?.focus(match.id);
    }
  };
  const selectNode = (id: string) => {
    setSelectedId(id);
    rendererRef.current?.focus(id);
  };

  const kinds = [settings.institutions && "institutions", settings.authors && "authors"].filter(
    Boolean,
  );
  const emptyMessage =
    props.notice ??
    (papers.length === 0
      ? "No paper matches these settings."
      : graph.nodes.length > 0
        ? null
        : kinds.length === 0
          ? "Turn on institutions or authors in the graph settings."
          : `No ${kinds.join(" or ")} to show. Affiliations come from the papers' HTML pages; ` +
            `${affiliatedCount} of these ${shownPapers.length} papers have some so far.`);

  return (
    <div class="graph">
      <canvas
        ref={canvasRef}
        class="graph__canvas"
        role="img"
        aria-label="Graph of the institutions and authors of the loaded papers, linked when they share a paper"
      />

      {emptyMessage && <p class="graph__empty">{emptyMessage}</p>}

      {selected && (
        <aside class="graph__details" aria-label="Details">
          <button
            type="button"
            class="graph__close"
            aria-label="Close"
            onClick={() => setSelectedId(null)}
          >
            ×
          </button>
          <p class="graph__kind">{selected.kind === "institution" ? "Institution" : "Author"}</p>
          <h2>{selected.label}</h2>
          <p class="muted">
            {selected.paperIds.length} paper{selected.paperIds.length > 1 ? "s" : ""}
          </p>
          <ul class="graph__papers">
            {selected.paperIds.slice(0, DETAILS_PAPERS).map((id) => {
              const paper = papersById.get(id);
              return paper ? (
                <li key={id}>
                  <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
                    {paper.title}
                  </a>{" "}
                  <span class="muted">· {formatDay(paper.announced)}</span>
                </li>
              ) : null;
            })}
          </ul>
          {connections.length > 0 && (
            <>
              <p class="graph__kind">Most connected</p>
              <ul class="graph__connections">
                {connections.map(({ node, weight }) => (
                  <li key={node.id}>
                    <button type="button" class="link-button" onClick={() => selectNode(node.id)}>
                      {node.label}
                    </button>{" "}
                    <span class="muted">
                      {weight} shared paper{weight > 1 ? "s" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <button
            type="button"
            class="button"
            onClick={() => onShowPapers(selected.kind, selected.label)}
          >
            Show all {selected.paperIds.length} papers
          </button>
        </aside>
      )}

      <GraphSettingsPanel
        open={panelOpen}
        onToggle={() => setPanelOpen(!panelOpen)}
        highlight={highlight}
        highlightInput={highlightInput}
        onHighlight={setHighlight}
        onHighlightSubmit={focusFirstMatch}
        categories={props.categories}
        category={props.category}
        onCategory={props.onCategory}
        storeDays={props.storeDays}
        period={props.period}
        onPeriod={props.onPeriod}
        query={props.query}
        onQuery={props.onQuery}
        venues={props.venues}
        venue={props.venue}
        onVenue={props.onVenue}
        paperCount={shownPapers.length}
        affiliatedCount={affiliatedCount}
        settings={settings}
        onSettings={changeSettings}
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
        onFit={() => rendererRef.current?.fit()}
        onReset={() => changeSettings(DEFAULT_GRAPH_SETTINGS)}
      />

      <div class="graph__legend">
        {settings.institutions && (
          <span>
            <i class="graph__dot graph__dot--institution" />
            Institutions ({institutionCount.toLocaleString()})
          </span>
        )}
        {settings.authors && (
          <span>
            <i class="graph__dot graph__dot--author" />
            Authors ({(graph.nodes.length - institutionCount).toLocaleString()})
          </span>
        )}
        <span>{graph.links.length.toLocaleString()} links</span>
      </div>
      <p class="graph__hint">
        drag · scroll to zoom · click = details · double-click = papers · linked when they share a
        paper
      </p>
    </div>
  );
}
