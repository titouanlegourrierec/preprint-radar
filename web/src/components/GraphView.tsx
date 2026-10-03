import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { formatDay } from "../format";
import { buildGraph, type EntityKind, type GraphNode, isEntity, nodeMatches } from "../graph";
import { GraphRenderer } from "../graph-renderer";
import { isTyping } from "../keyboard";
import type { Period } from "../period";
import {
  DEFAULT_GRAPH_SETTINGS,
  type GraphSettings,
  loadGraphSettings,
  saveGraphSettings,
} from "../preferences";
import type { FacetCount } from "../search";
import { searchKey } from "../text";
import type { ArchiveSummary, DaySummary, Paper } from "../types";
import { GraphSettingsPanel } from "./GraphSettingsPanel";

const DETAILS_PAPERS = 8;
const DETAILS_CONNECTIONS = 8;
const DETAILS_AUTHORS = 8;
const KIND_NAMES = { paper: "Paper", institution: "Institution", author: "Author" } as const;
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
  /** Years of the archive of highly cited papers. */
  archiveYears: ArchiveSummary[];
  /** The archive year shown, `null` for the recent days. */
  archiveYear: number | null;
  onArchiveYear: (year: number | null) => void;
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
}

/** Full-screen co-occurrence graph of the institutions and authors of the loaded papers. */
export function GraphView(props: Props) {
  const { papers, onShowPapers, onOpenPaper, theme, citations } = props;
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
        papers: settings.papers,
        institutions: settings.institutions,
        authors: settings.authors,
        isolated: settings.isolated,
        minPapers: { institution: settings.minInstitutionPapers, author: settings.minAuthorPapers },
        maxNodes: settings.maxNodes > 0 ? settings.maxNodes : Number.POSITIVE_INFINITY,
        citations,
      }),
    [
      shownPapers,
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
  const selected = (selectedId && nodesById.get(selectedId)) || null;
  // Nodes of each paper, to find who shares papers when papers are nodes themselves.
  const entitiesByPaper = useMemo(() => {
    const byPaper = new Map<string, GraphNode[]>();
    for (const node of graph.nodes) {
      if (node.kind === "paper") continue;
      for (const id of node.paperIds) byPaper.set(id, [...(byPaper.get(id) ?? []), node]);
    }
    return byPaper;
  }, [graph]);
  const connections = useMemo(() => {
    if (!selected || selected.kind === "paper") return [];
    if (settings.papers) {
      const shared = new Map<GraphNode, number>();
      for (const id of selected.paperIds) {
        for (const node of entitiesByPaper.get(id) ?? []) {
          if (node !== selected) shared.set(node, (shared.get(node) ?? 0) + 1);
        }
      }
      return [...shared]
        .map(([node, weight]) => ({ node, weight }))
        .sort((a, b) => b.weight - a.weight || b.node.paperIds.length - a.node.paperIds.length)
        .slice(0, DETAILS_CONNECTIONS);
    }
    return graph.links
      .filter((link) => link.source === selected.id || link.target === selected.id)
      .map((link) => ({
        node: nodesById.get(link.source === selected.id ? link.target : link.source),
        weight: link.weight,
      }))
      .filter((entry): entry is { node: GraphNode; weight: number } => entry.node !== undefined)
      .sort((a, b) => b.weight - a.weight || b.node.paperIds.length - a.node.paperIds.length)
      .slice(0, DETAILS_CONNECTIONS);
  }, [graph, nodesById, selected, settings.papers, entitiesByPaper]);
  // A paper can be selected without being a node (no institution or author to link it to).
  const selectedPaper = selectedId?.startsWith("paper:")
    ? papersById.get(selectedId.slice("paper:".length))
    : undefined;

  // The renderer is imperative: create it once, then push every change to it.
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const highlightInput = useRef<HTMLInputElement>(null);
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
  const selectedEntity = selected && isEntity(selected) ? selected : null;
  const emptyMessage =
    props.notice ??
    (papers.length === 0
      ? "No paper matches these settings."
      : graph.nodes.length > 0
        ? null
        : kinds.length === 0
          ? "Turn on institutions or authors in the graph settings."
          : `No ${kinds.join(" or ")} to show: ${affiliatedCount} of these ` +
            `${shownPapers.length} papers have known affiliations so far.`);

  return (
    <div class="graph">
      <canvas
        ref={canvasRef}
        class="graph__canvas"
        role="img"
        aria-label="Graph of the loaded papers with their institutions and authors"
      />

      {emptyMessage && <p class="graph__empty">{emptyMessage}</p>}

      {(selected || selectedPaper) && (
        <aside class="graph__details" aria-label="Details">
          <button
            type="button"
            class="graph__close"
            aria-label="Close"
            onClick={() => setSelectedId(null)}
          >
            ×
          </button>
          <p class="graph__kind">{KIND_NAMES[selected?.kind ?? "paper"]}</p>
          {selectedPaper ? (
            <PaperDetails
              paper={selectedPaper}
              absent={
                selected
                  ? null
                  : !settings.papers
                    ? "Papers are hidden: turn them on in the graph settings to see this one."
                    : !selectedPaper.affiliations?.length && !settings.authors
                      ? "No affiliations are known for this paper yet: turn on Authors to see it with its authors."
                      : "Not in the graph with these settings: its institutions and authors are filtered out."
              }
              citations={citations.get(selectedPaper.arxiv_id)}
              onOpen={() => onOpenPaper(selectedPaper)}
            />
          ) : (
            selectedEntity && (
              <>
                <h2>{selectedEntity.label}</h2>
                <p class="muted" title="Over the papers shown: the period or year, and the search">
                  {plural(selectedEntity.paperIds.length, "paper")} ·{" "}
                  {plural(selectedEntity.citations, "citation")}
                </p>
                <ul class="graph__papers">
                  {byCitationCount(selectedEntity.paperIds, citations)
                    .slice(0, DETAILS_PAPERS)
                    .map((id) => {
                      const paper = papersById.get(id);
                      const count = citations.get(id);
                      return paper ? (
                        <li key={id}>
                          <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
                            {paper.title}
                          </a>{" "}
                          <span class="muted">
                            · {formatDay(paper.announced)}
                            {count !== undefined && ` · ${plural(count, "citation")}`}
                          </span>
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
                          <button
                            type="button"
                            class="link-button"
                            onClick={() => selectNode(node.id)}
                          >
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
                  onClick={() => onShowPapers(selectedEntity.kind, selectedEntity.label)}
                >
                  Show all {selectedEntity.paperIds.length} papers
                </button>
              </>
            )
          )}
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
        archiveYears={props.archiveYears}
        archiveYear={props.archiveYear}
        onArchiveYear={props.onArchiveYear}
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
        onFit={() => rendererRef.current?.fit()}
        onReset={() => changeSettings(DEFAULT_GRAPH_SETTINGS)}
      />

      <div class="graph__legend">
        {(
          [
            ["paper", "Papers"],
            ["institution", "Institutions"],
            ["author", "Authors"],
          ] as const
        ).map(
          ([kind, name]) =>
            counts[kind] > 0 && (
              <span key={kind}>
                <i class={`graph__dot graph__dot--${kind}`} />
                {name} ({counts[kind].toLocaleString()})
              </span>
            ),
        )}
        <span>{graph.links.length.toLocaleString()} links</span>
      </div>
      <p class="graph__hint">
        drag · scroll to zoom · click = details · double-click = open in the list
      </p>
    </div>
  );
}

/** "1 paper", "12 papers". */
function plural(count: number, noun: string): string {
  return `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;
}

/** Paper ids, most cited first; unknown counts last, and ties keep their order. */
function byCitationCount(ids: readonly string[], citations: ReadonlyMap<string, number>): string[] {
  return [...ids].sort((a, b) => (citations.get(b) ?? -1) - (citations.get(a) ?? -1));
}

/** Details of a selected paper: what it is, who wrote it, where, and a way to read it. */
function PaperDetails({
  paper,
  absent,
  citations,
  onOpen,
}: {
  paper: Paper;
  /** Why the paper has no node, if it has none. */
  absent: string | null;
  /** Its citation count, when known. */
  citations: number | undefined;
  onOpen: () => void;
}) {
  const authors = paper.authors.slice(0, DETAILS_AUTHORS).join(", ");
  const hidden = paper.authors.length - DETAILS_AUTHORS;
  return (
    <>
      <h2>
        <a href={paper.abs_url} target="_blank" rel="noopener noreferrer">
          {paper.title}
        </a>
      </h2>
      <p class="muted">
        {formatDay(paper.announced)}
        {paper.venue && ` · ${paper.venue}`}
        {citations !== undefined && ` · ${plural(citations, "citation")}`}
      </p>
      <p>
        {authors}
        {hidden > 0 && <span class="muted"> +{hidden}</span>}
      </p>
      {(paper.affiliations ?? []).length > 0 && (
        <ul class="graph__connections">
          {(paper.affiliations ?? []).map((affiliation) => (
            <li key={affiliation}>{affiliation}</li>
          ))}
        </ul>
      )}
      {absent && <p class="muted">{absent}</p>}
      <button type="button" class="button" onClick={onOpen}>
        Open in the list
      </button>
    </>
  );
}
