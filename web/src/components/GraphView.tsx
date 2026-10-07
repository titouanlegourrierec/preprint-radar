import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { YearRange } from "../archive-years";
import { download, downloadBlob } from "../download";
import { countOf, formatDay } from "../format";
import {
  buildGraph,
  type EntityKind,
  type GraphNode,
  isEntity,
  MAX_CLIQUE_AUTHORS,
  nodeMatches,
  papersOfNode,
  replaySteps,
  severalPeople,
  sharedPapers,
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
  const { papers, onShowPapers, onOpenPaper, theme, citations, focus, onFocus } = props;
  const [settings, setSettings] = useState<GraphSettings>(loadGraphSettings);
  const [panelOpen, setPanelOpen] = useState(() => window.matchMedia(WIDE_SCREEN).matches);
  const [highlight, setHighlight] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cutoff, setCutoff] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [introRead, setIntroRead] = useState(loadGraphIntroRead);
  // The connection whose shared papers are listed in the details.
  const [openConnection, setOpenConnection] = useState<string | null>(null);

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
  const matches = useMemo(
    () => (highlighted ? graph.nodes.filter((node) => highlighted.has(node.id)) : []),
    [graph, highlighted],
  );
  // The match shown by Enter or the list, `null` until one is; new matches start over.
  const [matchIndex, setMatchIndex] = useState<number | null>(null);
  useEffect(() => setMatchIndex(null), [matches]);
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
  const focusLabel = focus
    ? (nodesById.get(focus)?.label ?? focus.slice(focus.indexOf(":") + 1))
    : null;
  const fileName = exportName(new Date().toISOString().slice(0, 10), focus);
  const exportGraphML = () =>
    download(`${fileName}.graphml`, toGraphML(graph), "application/graphml+xml");
  const exportPng = async () => {
    const blob = await rendererRef.current?.toPng();
    if (blob) downloadBlob(`${fileName}.png`, blob);
  };
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
          {focusLabel} and{" "}
          {focusedPapers.length === 1
            ? "its paper"
            : `its ${countOf(focusedPapers.length, "paper")}`}
          , with their institutions and authors.{" "}
          <button type="button" class="link-button" onClick={() => onFocus(null)}>
            Show everything
          </button>
        </p>
      )}

      {(selected || selectedPaper) && (
        <aside class="graph__details" aria-label="Details" ref={detailsRef} tabIndex={-1}>
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
                  {countOf(selectedEntity.paperIds.length, "paper")} ·{" "}
                  {countOf(selectedEntity.citations, "citation")}
                  {selectedEntity.rorId && (
                    <>
                      {" · "}
                      <a
                        href={`https://ror.org/${selectedEntity.rorId}`}
                        title="This institution in the Research Organization Registry"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        ROR
                      </a>
                    </>
                  )}
                </p>
                {selectedEntity.people && (
                  <p class="muted">{severalPeople(selectedEntity.people)}</p>
                )}
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
                            {count !== undefined && ` · ${countOf(count, "citation")}`}
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
                          <button
                            type="button"
                            class="link-button muted"
                            aria-expanded={openConnection === node.id}
                            title="The papers they share"
                            onClick={() =>
                              setOpenConnection(openConnection === node.id ? null : node.id)
                            }
                          >
                            {countOf(weight, "shared paper")}
                          </button>
                          {openConnection === node.id && (
                            <ul class="graph__shared">
                              {byCitationCount(sharedPapers(selectedEntity, node), citations).map(
                                (id) => {
                                  const paper = papersById.get(id);
                                  return paper ? (
                                    <li key={id}>
                                      <a
                                        href={paper.abs_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                      >
                                        {paper.title}
                                      </a>
                                    </li>
                                  ) : null;
                                },
                              )}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                <div class="graph__actions">
                  <button
                    type="button"
                    class="button"
                    onClick={() => onShowPapers(selectedEntity.kind, selectedEntity.label)}
                  >
                    {selectedEntity.paperIds.length === 1
                      ? "Show its paper"
                      : `Show all ${countOf(selectedEntity.paperIds.length, "paper")}`}
                  </button>
                  {focus !== selectedEntity.id && (
                    <button
                      type="button"
                      class="button"
                      title="The graph of its papers alone: with whom it publishes"
                      onClick={() => onFocus(selectedEntity.id)}
                    >
                      Focus on this
                    </button>
                  )}
                </div>
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
        {graph.consortia > 0 && (
          <span>
            {countOf(graph.consortia, "paper")} of over {MAX_CLIQUE_AUTHORS} authors, whose authors
            are not linked to one another
          </span>
        )}
      </div>
      <p class="graph__hint">
        {coarse
          ? "drag · pinch to zoom · tap = details · double-tap = open in the list"
          : "drag · scroll to zoom · click = details · double-click = open in the list"}
      </p>
    </main>
  );
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
        {citations !== undefined && ` · ${countOf(citations, "citation")}`}
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
