import { type Graph, type GraphNode, type NodeKind, sameLayout } from "./graph";
import { initialPositions, inLargestComponent } from "./graph-layout";
import type { ForceSettings, FromLayout, LayoutGraph, ToLayout } from "./graph-simulation";

/** Force and display settings, as chosen in the graph settings panel. */
export interface RendererSettings {
  /** Pull towards the center, from 0 to 1. */
  centerForce: number;
  /** Repulsion between nodes. */
  repelForce: number;
  /** Stiffness of links, as a multiple of the default. */
  linkForce: number;
  /** Rest length of links between node borders, in graph units. */
  linkDistance: number;
  /** Node radius, as a multiple of the default. */
  nodeSize: number;
  /** What node areas show: the number of papers (papers all alike), or citations. */
  sizeBy: NodeSizing;
  /** On-screen size from which nodes get a label, as a multiple of the default. */
  labelThreshold: number;
}

export type NodeSizing = "papers" | "citations";

export interface RendererCallbacks {
  /** A node was clicked, or the background (`null`). */
  onSelect: (id: string | null) => void;
  /** A node was double-clicked. */
  onOpen: (id: string) => void;
}

/** Screen widths covered by overlays on each side of the canvas. */
export interface Overlays {
  /** Covered only while a node is selected (its details are shown there). */
  left: number;
  right: number;
}

export interface View {
  x: number;
  y: number;
  k: number;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

interface SimNode {
  id: string;
  node: GraphNode;
  /** Position among the nodes of the same kind, biggest first. */
  rank: number;
  /** Radius before the node size setting is applied. */
  baseRadius: number;
  radius: number;
  degree: number;
  /** Position, as the layout worker last sent it. */
  x: number;
  y: number;
}

interface SimLink {
  source: SimNode;
  target: SimNode;
  weight: number;
}

/**
 * The links and nodes of a view, batched by style, for one geometry: a hover or a highlight
 * draws them dimmed as they are, and builds only the few links and nodes it lights (PERF-5).
 */
interface Scene {
  key: string;
  links: { thin: Path2D; medium: Path2D; thick: Path2D };
  nodes: Record<NodeKind, Path2D>;
}

const KINDS: readonly NodeKind[] = ["paper", "institution", "author"];

/** A node's shape, in graph coordinates, at least `minRadius` big. */
function addShape(path: Path2D, node: SimNode, minRadius: number): void {
  const r = Math.max(node.radius, minRadius);
  if (node.node.kind === "paper") {
    // Papers are squares, so that they read apart from the people and places.
    path.rect(node.x - r, node.y - r, 2 * r, 2 * r);
  } else {
    path.moveTo(node.x + r, node.y);
    path.arc(node.x, node.y, r, 0, 2 * Math.PI);
  }
}

type Gesture =
  | { kind: "drag"; node: SimNode; startX: number; startY: number; moved: boolean }
  | { kind: "pan"; startX: number; startY: number; viewX: number; viewY: number; moved: boolean }
  | { kind: "pinch"; from: [Point, Point]; view: View };

interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

const MIN_ZOOM = 0.02;
const MAX_ZOOM = 8;
const MAX_FIT_ZOOM = 2;
const FIT_PADDING_PX = 48;
const FOCUS_ZOOM = 1.5;
const CLICK_TOLERANCE_PX = 4;
/** Beyond this many links, links are drawn fainter. */
const DENSE_LINKS = 3000;
/** The biggest nodes of each kind always have a label. */
const ALWAYS_LABELLED = 10;
const MAX_LABELS = 250;
/** On-screen radius from which a node is labelled, at label threshold 1. */
const LABEL_RADIUS_PX = 9;
/** Nodes never get smaller than this on screen, so that zooming out keeps them visible. */
const MIN_SCREEN_RADIUS_PX = 1.5;
const MAX_RADIUS = 28;
const LABEL_FONT_PX = 12;
const MAX_LABEL_LENGTH = 40;
/** On-screen radius from which an institution shows its logo (PROD-23), as labels grow. */
const LOGO_RADIUS_PX = 10;
/**
 * The ring of its node's color around a logo's white disc: a share of the node's radius on a
 * small node, at most a few pixels on screen on a big one.
 */
const LOGO_RING = 0.2;
const LOGO_RING_PX = 3;
/** The logo inside its disc, a little away from the edge. */
const LOGO_MARGIN = 0.92;
/** White in both themes, as the logos' tiles in the lists: dark marks stay readable. */
const LOGO_BACKGROUND = "#fff";

/**
 * Where a logo of `width` by `height` goes in a disc of radius `r` centered on (`x`, `y`):
 * the largest box of its proportions the disc holds, its corners on a circle a little inside
 * (`LOGO_MARGIN`), so that a wide mark gets the disc's width and a square one its square.
 */
export function logoBox(
  x: number,
  y: number,
  r: number,
  width: number,
  height: number,
): { x: number; y: number; w: number; h: number } {
  const ratio = width / height;
  const h = (2 * r * LOGO_MARGIN) / Math.sqrt(1 + ratio * ratio);
  const w = h * ratio;
  return { x: x - w / 2, y: y - h / 2, w, h };
}

/**
 * Radius of a node with `papers` papers. The area grows with the paper count, on the same
 * scale whatever the graph, so that a node with one paper stays small.
 */
/**
 * The links between two nodes (UX-61): their own, and those through the nodes both link to
 * (the papers two institutions share), from each node's links.
 */
export function peekLinks<L extends { source: { id: string }; target: { id: string } }>(
  from: string,
  to: string,
  linksOf: ReadonlyMap<string, readonly L[]>,
): L[] {
  const other = (link: L, end: string) =>
    link.source.id === end ? link.target.id : link.source.id;
  const fromLinks = linksOf.get(from) ?? [];
  const toLinks = linksOf.get(to) ?? [];
  const toNear = new Set(toLinks.map((link) => other(link, to)));
  const shared = new Set(fromLinks.map((link) => other(link, from)).filter((id) => toNear.has(id)));
  return [
    ...fromLinks.filter((link) => other(link, from) === to || shared.has(other(link, from))),
    ...toLinks.filter((link) => shared.has(other(link, to))),
  ];
}

export function nodeRadius(papers: number): number {
  return Math.min(MAX_RADIUS, 2.5 + 3.5 * Math.sqrt(Math.max(0, papers - 1)));
}

/**
 * Radius of a node with `citations` citations. Counts span five orders of magnitude, and
 * on recent papers the telling differences are 1, 5 or 30: the radius grows with their
 * logarithm, on the same scale whatever the graph, up to the same cap (reached at about 360).
 */
export function citationRadius(citations: number): number {
  return Math.min(MAX_RADIUS, 2.5 + 3 * Math.log2(1 + Math.max(0, citations)));
}

/** Radius of a node under a sizing, before the node size setting. */
function sizedRadius(node: GraphNode, sizeBy: NodeSizing): number {
  return sizeBy === "citations" ? citationRadius(node.citations) : nodeRadius(node.paperIds.length);
}

/** View transform that fits `bounds` in the part of the canvas not covered by overlays. */
export function fitTransform(
  bounds: Bounds,
  width: number,
  height: number,
  overlays: Overlays = { left: 0, right: 0 },
): View {
  const free = Math.max(1, width - overlays.left - overlays.right);
  const k = Math.min(
    MAX_FIT_ZOOM,
    Math.max(
      MIN_ZOOM,
      Math.min(
        (free - 2 * FIT_PADDING_PX) / Math.max(1, bounds.maxX - bounds.minX),
        (height - 2 * FIT_PADDING_PX) / Math.max(1, bounds.maxY - bounds.minY),
      ),
    ),
  );
  return {
    k,
    x: overlays.left + free / 2 - ((bounds.minX + bounds.maxX) / 2) * k,
    y: height / 2 - ((bounds.minY + bounds.maxY) / 2) * k,
  };
}

/** The view zoomed by `factor` about the screen point (x, y), within the zoom limits. */
export function zoomAbout(view: View, x: number, y: number, factor: number): View {
  const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.k * factor));
  const gx = (x - view.x) / view.k;
  const gy = (y - view.y) / view.k;
  return { k, x: x - gx * k, y: y - gy * k };
}

export interface Point {
  x: number;
  y: number;
}

/**
 * The view of a pinch: two fingers that started at `from` (on the view `start`) and are now
 * at `to`. It zooms by the ratio of their distances about their first midpoint, and pans
 * with the midpoint, so that the graph stays under the fingers.
 */
export function pinchView(
  start: View,
  from: readonly [Point, Point],
  to: readonly [Point, Point],
): View {
  const distance = ([a, b]: readonly [Point, Point]) =>
    Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
  const middle = ([a, b]: readonly [Point, Point]) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const [m0, m1] = [middle(from), middle(to)];
  const zoomed = zoomAbout(start, m0.x, m0.y, distance(to) / distance(from));
  return { ...zoomed, x: zoomed.x + m1.x - m0.x, y: zoomed.y + m1.y - m0.y };
}

function readColors() {
  const style = getComputedStyle(document.documentElement);
  const value = (name: string) => style.getPropertyValue(name).trim();
  return {
    paper: value("--graph-paper"),
    institution: value("--graph-institution"),
    author: value("--graph-author"),
    edge: value("--graph-edge"),
    accent: value("--accent"),
    label: value("--text"),
    halo: value("--surface"),
    font: getComputedStyle(document.body).fontFamily,
  };
}

function overlaps(box: Box, others: readonly Box[]): boolean {
  return others.some(
    (other) => other.x0 < box.x1 && box.x0 < other.x1 && other.y0 < box.y1 && box.y0 < other.y1,
  );
}

/**
 * Draws a force-directed graph on a canvas and handles panning, zooming, dragging and
 * selection. Drawing is batched into a few paths per frame, so that thousands of nodes
 * and tens of thousands of links stay interactive.
 */
export class GraphRenderer {
  private readonly canvas: HTMLCanvasElement;
  private readonly context: CanvasRenderingContext2D;
  private readonly callbacks: RendererCallbacks;
  private settings: RendererSettings;
  /** Runs the force layout off the main thread (`graph-worker.ts`). */
  private readonly layout = new Worker(new URL("./graph-worker.ts", import.meta.url), {
    type: "module",
  });
  /** The graph whose positions the layout sends; older ones are ignored. */
  private generation = 0;
  /** The graph shown, as last set. */
  private graph: Graph | null = null;
  private nodes: SimNode[] = [];
  private links: SimLink[] = [];
  private byId = new Map<string, SimNode>();
  private neighbors = new Map<string, Set<string>>();
  /** Each node's links, which its focus draws in the accent. */
  private linksOf = new Map<string, SimLink[]>();
  /** Bumped whenever a node moves or is sized again: the scene is then built again (PERF-5). */
  private geometry = 0;
  private scene: Scene | null = null;
  /** Last known position of every node seen so far, reused when the graph changes. */
  private readonly positions = new Map<string, { x: number; y: number }>();
  private view: View = { x: 0, y: 0, k: 1 };
  /** Keep the whole graph in view until the user pans or zooms. */
  private autoFit = true;
  /** Node kept at the center while the layout settles, until the user moves the view. */
  private followed: string | null = null;
  private overlays: Overlays = { left: 0, right: 0 };
  private hovered: string | null = null;
  private selected: string | null = null;
  private highlighted: ReadonlySet<string> | null = null;
  private peeked: string | null = null;
  private colors = readColors();
  /** Each major institution's logo, by its name (PROD-23). */
  private logoOf: ((institution: string) => string | undefined) | undefined;
  /** The institution nodes that have a logo, so that a frame looks at these only. */
  private logoNodes: { node: SimNode; url: string }[] = [];
  /** The logos' images, each asked for once, when a node first shows it. */
  private readonly logoImages = new Map<string, HTMLImageElement>();
  private gesture: Gesture | null = null;
  /** Pointers down on the canvas, by id, at their latest screen position. */
  private readonly pointers = new Map<number, Point>();
  private frame = 0;
  /**
   * A new graph whose first positions have not come yet: the layout opens it out of sight
   * (UX-30), and the canvas keeps its former frame until it fades the graph in.
   */
  private revealing = false;
  private readonly reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  private readonly cleanups: (() => void)[] = [];

  /**
   * The graph as drawn, as a PNG on the page's background (the canvas itself is
   * transparent), for slides (§17.1 #8). `null` if the browser refuses.
   */
  toPng(): Promise<Blob | null> {
    const image = document.createElement("canvas");
    image.width = this.canvas.width;
    image.height = this.canvas.height;
    const context = image.getContext("2d");
    if (!context) return Promise.resolve(null);
    context.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    context.fillRect(0, 0, image.width, image.height);
    context.drawImage(this.canvas, 0, 0);
    return new Promise((resolve) => image.toBlob(resolve, "image/png"));
  }

  constructor(canvas: HTMLCanvasElement, callbacks: RendererCallbacks, settings: RendererSettings) {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("This browser cannot draw on a canvas.");
    this.canvas = canvas;
    this.context = context;
    this.callbacks = callbacks;
    this.settings = settings;

    this.layout.addEventListener("message", (event: MessageEvent<FromLayout>) =>
      this.onPositions(event.data),
    );
    // Said, not swallowed: the graph would stay at its starting positions.
    this.layout.addEventListener("error", (event) =>
      console.error(`The graph layout failed: ${event.message}`),
    );

    const observer = new ResizeObserver(() => this.resize());
    observer.observe(canvas);
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => {
      this.colors = readColors();
      this.requestDraw();
    };
    scheme.addEventListener("change", onScheme);
    this.cleanups.push(
      () => observer.disconnect(),
      () => scheme.removeEventListener("change", onScheme),
      this.listen("pointerdown", (event) => this.onPointerDown(event)),
      this.listen("pointermove", (event) => this.onPointerMove(event)),
      this.listen("pointerup", (event) => this.onPointerUp(event)),
      this.listen("pointercancel", (event) => this.onPointerUp(event)),
      this.listen("pointerleave", () => this.onPointerLeave()),
      this.listen("dblclick", (event) => this.onDoubleClick(event)),
      this.listen("wheel", (event) => this.onWheel(event), { passive: false }),
    );
    this.resize();
  }

  /**
   * Show a new graph, keeping the position of the nodes that were already there. One that
   * lays out as the graph shown (`sameLayout`: its citation counts arrived, PERF-7) only
   * updates what the nodes say, and their size when citations size them, as a new size does.
   */
  setGraph(graph: Graph): void {
    const shown = this.graph;
    this.graph = graph;
    if (shown && sameLayout(shown, graph)) {
      for (const [index, node] of graph.nodes.entries()) {
        const simNode = this.nodes[index];
        if (simNode) simNode.node = node;
      }
      if (this.settings.sizeBy === "citations") {
        this.applySizing();
        this.sendForces(true);
      }
      this.findLogoNodes();
      this.requestDraw();
      return;
    }
    this.savePositions();
    const degree = new Map<string, number>();
    for (const link of graph.links) {
      degree.set(link.source, (degree.get(link.source) ?? 0) + 1);
      degree.set(link.target, (degree.get(link.target) ?? 0) + 1);
    }

    this.nodes = graph.nodes.map((node) => ({
      id: node.id,
      node,
      rank: 0,
      baseRadius: 0,
      radius: 0,
      degree: degree.get(node.id) ?? 0,
      x: 0,
      y: 0,
    }));
    this.applySizing();
    this.findLogoNodes();
    this.byId = new Map(this.nodes.map((node) => [node.id, node]));
    this.neighbors = new Map(this.nodes.map((node) => [node.id, new Set<string>()]));
    this.linksOf = new Map(this.nodes.map((node) => [node.id, []]));
    this.links = [];
    for (const link of graph.links) {
      const source = this.byId.get(link.source);
      const target = this.byId.get(link.target);
      if (!source || !target) continue;
      const simLink = { source, target, weight: link.weight };
      this.links.push(simLink);
      this.neighbors.get(source.id)?.add(target.id);
      this.neighbors.get(target.id)?.add(source.id);
      this.linksOf.get(source.id)?.push(simLink);
      this.linksOf.get(target.id)?.push(simLink);
    }

    // Nodes seen before keep their position; new ones start next to their neighbors, or
    // component by component around the rest, so that a growing graph (time-lapse, lower
    // thresholds) stays stable and a new one settles quickly.
    const indexOf = new Map(this.nodes.map((node, index) => [node.id, index]));
    const pairs = this.links.map(
      ({ source, target }) => [indexOf.get(source.id) ?? 0, indexOf.get(target.id) ?? 0] as const,
    );
    const start = initialPositions(
      this.nodes.length,
      pairs,
      this.nodes.map((node) => this.positions.get(node.id)),
    );
    const main = inLargestComponent(this.nodes.length, pairs);
    let known = 0;
    for (const [index, node] of this.nodes.entries()) {
      if (this.positions.has(node.id)) known++;
      node.x = start[index]?.x ?? 0;
      node.y = start[index]?.y ?? 0;
    }
    this.geometry++;

    // A mostly new graph (other papers, authors turned on) is framed again from scratch,
    // once the layout has opened it.
    const fresh = known < this.nodes.length / 2;
    if (fresh) this.autoFit = true;
    this.revealing = fresh && !this.reducedMotion;
    if (this.autoFit) this.fitNow();
    this.requestDraw();
    const layout: LayoutGraph = {
      positions: Float32Array.from(this.nodes.flatMap((node) => [node.x, node.y])),
      radii: Float32Array.from(this.nodes, (node) => node.radius),
      degrees: Uint32Array.from(this.nodes, (node) => node.degree),
      main: Uint8Array.from(main, (inMain) => (inMain ? 1 : 0)),
      links: Uint32Array.from(pairs.flat()),
      weights: Float32Array.from(this.links, (link) => link.weight),
    };
    this.generation++;
    this.canvas.dataset.layout = "moving";
    this.send(
      {
        type: "graph",
        generation: this.generation,
        graph: layout,
        settings: this.forces(),
        // A mostly new graph cools to its equilibrium, one mostly laid out settles (UX-30).
        alpha: fresh ? 1 : 0.4,
        settle: this.reducedMotion,
      },
      Object.values(layout).map((array: ArrayBufferView) => array.buffer as ArrayBuffer),
    );
  }

  /** The logos institution nodes show once big enough on screen (PROD-23). */
  setLogos(logoOf: ((institution: string) => string | undefined) | undefined): void {
    this.logoOf = logoOf;
    this.findLogoNodes();
    this.requestDraw();
  }

  setSettings(settings: RendererSettings): void {
    const previous = this.settings;
    this.settings = settings;
    const resized = settings.nodeSize !== previous.nodeSize || settings.sizeBy !== previous.sizeBy;
    if (resized) this.applySizing();
    const forcesChanged =
      settings.centerForce !== previous.centerForce ||
      settings.repelForce !== previous.repelForce ||
      settings.linkForce !== previous.linkForce ||
      settings.linkDistance !== previous.linkDistance ||
      resized;
    if (forcesChanged) this.sendForces(resized);
    this.requestDraw();
  }

  /** The forces to the layout, which settles into them, with the nodes' radii if `resized`. */
  private sendForces(resized: boolean): void {
    if (this.nodes.length === 0) return;
    this.send({
      type: "forces",
      settings: this.forces(),
      ...(resized ? { radii: Float32Array.from(this.nodes, (node) => node.radius) } : {}),
      alpha: 0.3,
      settle: this.reducedMotion,
    });
  }

  /**
   * Size the nodes for the current settings, and rank them by that size within their kind:
   * the biggest ones always get a label.
   */
  private applySizing(): void {
    const { sizeBy, nodeSize } = this.settings;
    for (const node of this.nodes) {
      node.baseRadius = sizedRadius(node.node, sizeBy);
      node.radius = node.baseRadius * nodeSize;
    }
    const measure = (node: SimNode) =>
      sizeBy === "citations" ? node.node.citations : node.node.paperIds.length;
    // Stable: equal nodes keep the graph's order (most frequent first).
    const ranked = [...this.nodes].sort((a, b) => measure(b) - measure(a));
    const ranks = { paper: 0, institution: 0, author: 0 };
    for (const node of ranked) node.rank = ranks[node.node.kind]++;
    this.geometry++;
  }

  /** Emphasize some nodes (e.g. search matches), dimming the others; `null` clears. */
  setHighlight(ids: ReadonlySet<string> | null): void {
    this.highlighted = ids;
    this.requestDraw();
  }

  setSelected(id: string | null): void {
    this.selected = id;
    this.requestDraw();
  }

  /**
   * Point at a node from the details (UX-61), as their rows are hovered or focused: a ring,
   * its label first, and its links to the focus in bold; `null` clears.
   */
  setPeek(id: string | null): void {
    if (this.peeked === id) return;
    this.peeked = id;
    this.requestDraw();
  }

  /** Declare the overlays, so that fitting and revealing nodes avoid them. */
  /** Re-read the palette from the CSS variables and redraw, after a theme change. */
  refreshTheme(): void {
    this.colors = readColors();
    this.requestDraw();
  }

  setOverlays(overlays: Overlays): void {
    this.overlays = overlays;
    if (this.autoFit) {
      this.fitNow();
      this.requestDraw();
    }
  }

  /** Center the view on a node. */
  focus(id: string): void {
    const node = this.byId.get(id);
    if (!node) return;
    this.centerOn(node, Math.max(this.view.k, FOCUS_ZOOM));
    this.autoFit = false;
    this.followed = id;
    this.requestDraw();
  }

  /** Zoom to show the whole graph, and keep it in view while the layout settles. */
  fit(): void {
    this.autoFit = true;
    this.followed = null;
    this.fitNow();
    this.requestDraw();
  }

  /** Zoom by `factor` about the middle of the part of the canvas not covered by overlays. */
  zoomBy(factor: number): void {
    const free = this.canvas.clientWidth - this.overlays.left - this.overlays.right;
    this.autoFit = false;
    this.followed = null;
    this.view = zoomAbout(
      this.view,
      this.overlays.left + free / 2,
      this.canvas.clientHeight / 2,
      factor,
    );
    this.requestDraw();
  }

  /**
   * Shake the layout, which settles back (UX-30): gently, from alpha 0.5, since it is at its
   * equilibrium already; at once under reduced motion.
   */
  reheat(alpha = 0.5): void {
    this.send({ type: "heat", alpha, settle: this.reducedMotion });
  }

  destroy(): void {
    this.layout.terminate();
    cancelAnimationFrame(this.frame);
    for (const cleanup of this.cleanups) cleanup();
  }

  private send(message: ToLayout, transfer: Transferable[] = []): void {
    this.layout.postMessage(message, transfer);
  }

  private forces(): ForceSettings {
    const { centerForce, repelForce, linkForce, linkDistance } = this.settings;
    return { centerForce, repelForce, linkForce, linkDistance };
  }

  /** New positions from the layout: follow or fit them, and draw. */
  private onPositions({ generation, positions, moving }: FromLayout): void {
    if (generation !== this.generation) return;
    const dragged = this.gesture?.kind === "drag" ? this.gesture.node : null;
    for (const [index, node] of this.nodes.entries()) {
      if (node === dragged) continue;
      node.x = positions[2 * index] ?? node.x;
      node.y = positions[2 * index + 1] ?? node.y;
    }
    this.geometry++;
    const followed = this.followed === null ? undefined : this.byId.get(this.followed);
    if (followed) this.centerOn(followed, this.view.k);
    else if (this.autoFit) this.fitNow();
    if (this.revealing) {
      this.revealing = false;
      // Restarts the fade: the class comes off, a layout is forced, and it goes back on.
      this.canvas.classList.remove("graph__canvas--reveal");
      void this.canvas.offsetWidth;
      this.canvas.classList.add("graph__canvas--reveal");
    }
    // Moving again after Reheat, new forces or a drag, as for a new graph.
    this.canvas.dataset.layout = moving ? "moving" : "settled";
    if (!moving) this.savePositions();
    this.requestDraw();
  }

  private listen<K extends keyof HTMLElementEventMap>(
    type: K,
    handler: (event: HTMLElementEventMap[K]) => void,
    options?: AddEventListenerOptions,
  ): () => void {
    this.canvas.addEventListener(type, handler, options);
    return () => this.canvas.removeEventListener(type, handler, options);
  }

  private savePositions(): void {
    for (const node of this.nodes) this.positions.set(node.id, { x: node.x, y: node.y });
  }

  private bounds(): Bounds | null {
    if (this.nodes.length === 0) return null;
    const bounds = {
      minX: Number.POSITIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
      maxX: Number.NEGATIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
    };
    for (const node of this.nodes) {
      const x = node.x;
      const y = node.y;
      bounds.minX = Math.min(bounds.minX, x - node.radius);
      bounds.minY = Math.min(bounds.minY, y - node.radius);
      bounds.maxX = Math.max(bounds.maxX, x + node.radius);
      bounds.maxY = Math.max(bounds.maxY, y + node.radius);
    }
    return bounds;
  }

  private centerOn(node: SimNode, k: number): void {
    const center = (this.overlays.left + this.canvas.clientWidth - this.overlays.right) / 2;
    this.view = {
      k,
      x: center - node.x * k,
      y: this.canvas.clientHeight / 2 - node.y * k,
    };
  }

  private fitNow(): void {
    const bounds = this.bounds();
    if (bounds) {
      this.view = fitTransform(bounds, this.canvas.clientWidth, this.canvas.clientHeight, {
        left: this.selected === null ? 0 : this.overlays.left,
        right: this.overlays.right,
      });
    }
  }

  private resize(): void {
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(this.canvas.clientWidth * ratio);
    this.canvas.height = Math.round(this.canvas.clientHeight * ratio);
    if (this.autoFit) this.fitNow();
    this.draw();
  }

  private requestDraw(): void {
    if (this.frame === 0) this.frame = requestAnimationFrame(() => this.draw());
  }

  private draw(): void {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    // The former frame stays while the new graph opens out of sight.
    if (this.revealing) return;
    const { canvas, context, view, colors } = this;
    const ratio = window.devicePixelRatio || 1;
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    if (this.nodes.length === 0) return;

    // Visible area in graph coordinates: what lies outside is not drawn.
    const margin = 20 / view.k;
    const left = -view.x / view.k - margin;
    const top = -view.y / view.k - margin;
    const right = (canvas.clientWidth - view.x) / view.k + margin;
    const bottom = (canvas.clientHeight - view.y) / view.k + margin;

    const focus = this.hovered ?? this.selected;
    const near = focus === null ? undefined : this.neighbors.get(focus);
    const highlighted = this.highlighted;
    const peek = this.peeked !== null && this.byId.has(this.peeked) ? this.peeked : null;
    const isLit = (id: string): boolean =>
      id === peek ||
      (focus !== null
        ? id === focus || near?.has(id) === true
        : highlighted === null || highlighted.has(id));
    const dimmed = focus !== null || highlighted !== null;

    context.setTransform(ratio * view.k, 0, 0, ratio * view.k, ratio * view.x, ratio * view.y);

    const minRadius = MIN_SCREEN_RADIUS_PX / view.k;
    const scene = this.sceneFor({ left, top, right, bottom }, minRadius);
    const { thin, medium, thick } = scene.links;
    context.lineCap = "round";
    context.strokeStyle = colors.edge;
    // Fainter links when there are many, so that they do not turn into a gray fog.
    context.globalAlpha = dimmed
      ? 0.1
      : Math.max(0.2, 0.55 * Math.min(1, Math.sqrt(DENSE_LINKS / this.links.length)));
    for (const [path, width] of [
      [thin, 0.7],
      [medium, 1.2],
      [thick, 1.8],
    ] as const) {
      context.lineWidth = width / view.k;
      context.stroke(path);
    }
    if (focus !== null) {
      // The focus's links over the dimmed ones, in the accent: a few, built each frame.
      const focused = new Path2D();
      for (const { source, target } of this.linksOf.get(focus) ?? []) {
        focused.moveTo(source.x, source.y);
        focused.lineTo(target.x, target.y);
      }
      context.globalAlpha = 0.9;
      context.strokeStyle = colors.accent;
      context.lineWidth = 1.4 / view.k;
      context.stroke(focused);
      // The paths to the node pointed at from the details, bolder: its link to the focus,
      // or through the nodes both link to (the papers two institutions share).
      const peeked = new Path2D();
      for (const { source, target } of peek === null ? [] : peekLinks(focus, peek, this.linksOf)) {
        peeked.moveTo(source.x, source.y);
        peeked.lineTo(target.x, target.y);
      }
      context.globalAlpha = 1;
      context.lineWidth = 2.4 / view.k;
      context.stroke(peeked);
    }

    // Nodes, batched by color: faint under a focus or a highlight, the lit ones over them,
    // each with its logo as faint as itself.
    const inSight = { left, top, right, bottom };
    for (const kind of KINDS) {
      context.fillStyle = colors[kind];
      context.globalAlpha = dimmed ? 0.15 : 1;
      context.fill(scene.nodes[kind]);
    }
    this.drawLogos(inSight, dimmed ? (id) => !isLit(id) : () => true, dimmed ? 0.15 : 1);
    if (dimmed) {
      const lit: Record<NodeKind, Path2D> = {
        paper: new Path2D(),
        institution: new Path2D(),
        author: new Path2D(),
      };
      const shown = focus === null ? [...(highlighted ?? [])] : [focus, ...(near ?? [])];
      for (const id of peek === null ? shown : [...shown, peek]) {
        const node = this.byId.get(id);
        if (node) addShape(lit[node.node.kind], node, minRadius);
      }
      context.globalAlpha = 1;
      for (const kind of KINDS) {
        context.fillStyle = colors[kind];
        context.fill(lit[kind]);
      }
      this.drawLogos(inSight, isLit, 1);
    }
    // Rings: the node selected, and without a focus the highlighted ones.
    const rings = new Path2D();
    const ringGap = 2 / view.k;
    const ringed = new Set([
      ...(this.selected === null ? [] : [this.selected]),
      ...(peek === null ? [] : [peek]),
      ...(focus === null ? (highlighted ?? []) : []),
    ]);
    for (const id of ringed) {
      const node = this.byId.get(id);
      if (!node) continue;
      const r = Math.max(node.radius, minRadius) + ringGap;
      rings.moveTo(node.x + r, node.y);
      rings.arc(node.x, node.y, r, 0, 2 * Math.PI);
    }
    context.strokeStyle = colors.accent;
    context.lineWidth = 2 / view.k;
    context.stroke(rings);

    this.drawLabels({ left, top, right, bottom, focus, peek, isLit });
  }

  private findLogoNodes(): void {
    const logoOf = this.logoOf;
    this.logoNodes =
      logoOf === undefined
        ? []
        : this.nodes.flatMap((node) => {
            const url = node.node.kind === "institution" ? logoOf(node.node.label) : undefined;
            return url === undefined ? [] : [{ node, url }];
          });
  }

  /**
   * The logos of the institution nodes in sight and big enough on screen that `which`
   * picks, each on a white disc inside a ring of its node's color; an image is asked for
   * when its node first shows it, and drawn once it has come.
   */
  private drawLogos(
    bounds: { left: number; top: number; right: number; bottom: number },
    which: (id: string) => boolean,
    alpha: number,
  ): void {
    const { context, view } = this;
    const smallest = LOGO_RADIUS_PX / view.k;
    context.globalAlpha = alpha;
    for (const { node, url } of this.logoNodes) {
      const { x, y, radius } = node;
      if (radius < smallest || !which(node.id)) continue;
      if (
        x + radius < bounds.left ||
        x - radius > bounds.right ||
        y + radius < bounds.top ||
        y - radius > bounds.bottom
      ) {
        continue;
      }
      let image = this.logoImages.get(url);
      if (image === undefined) {
        image = new Image();
        image.decoding = "async";
        image.addEventListener("load", () => this.requestDraw());
        image.src = url;
        this.logoImages.set(url, image);
      }
      // Not come yet, failed, or an SVG this browser cannot size.
      if (!image.complete || image.naturalWidth === 0 || image.naturalHeight === 0) continue;
      const disc = radius - Math.min(radius * LOGO_RING, LOGO_RING_PX / view.k);
      context.fillStyle = LOGO_BACKGROUND;
      context.beginPath();
      context.arc(x, y, disc, 0, 2 * Math.PI);
      context.fill();
      const box = logoBox(x, y, disc, image.naturalWidth, image.naturalHeight);
      context.drawImage(image, box.x, box.y, box.w, box.h);
    }
  }

  /**
   * The links and nodes in sight, batched by style: kept while neither the view nor a node
   * moves, so that hovering a settled graph builds only what it lights (PERF-5).
   */
  private sceneFor(
    bounds: { left: number; top: number; right: number; bottom: number },
    minRadius: number,
  ): Scene {
    const { left, top, right, bottom } = bounds;
    const key = `${this.geometry} ${left} ${top} ${right} ${bottom} ${minRadius}`;
    if (this.scene?.key === key) return this.scene;
    const links = { thin: new Path2D(), medium: new Path2D(), thick: new Path2D() };
    for (const { source, target, weight } of this.links) {
      const sx = source.x;
      const sy = source.y;
      const tx = target.x;
      const ty = target.y;
      if (
        (sx < left && tx < left) ||
        (sx > right && tx > right) ||
        (sy < top && ty < top) ||
        (sy > bottom && ty > bottom)
      ) {
        continue;
      }
      const path = weight >= 3 ? links.thick : weight === 2 ? links.medium : links.thin;
      path.moveTo(sx, sy);
      path.lineTo(tx, ty);
    }
    const nodes: Record<NodeKind, Path2D> = {
      paper: new Path2D(),
      institution: new Path2D(),
      author: new Path2D(),
    };
    for (const node of this.nodes) {
      const r = Math.max(node.radius, minRadius);
      if (node.x + r < left || node.x - r > right || node.y + r < top || node.y - r > bottom) {
        continue;
      }
      addShape(nodes[node.node.kind], node, minRadius);
    }
    this.scene = { key, links, nodes };
    return this.scene;
  }

  /**
   * Labels keep a constant on-screen size. Without focus, the biggest nodes and those large
   * enough on screen get one; with a focus or a highlight, only the emphasized nodes do.
   * They are placed by priority, skipping any that would overlap a label already drawn.
   */
  private drawLabels(scene: {
    left: number;
    top: number;
    right: number;
    bottom: number;
    focus: string | null;
    peek: string | null;
    isLit: (id: string) => boolean;
  }): void {
    const { context, view, colors } = this;
    const { focus, isLit } = scene;
    const ratio = window.devicePixelRatio || 1;
    const threshold = LABEL_RADIUS_PX * this.settings.labelThreshold;
    // The focus's label first, then the node pointed at, then by rank.
    const first = [focus, scene.peek].flatMap((id) =>
      id === null ? [] : (this.byId.get(id) ?? []),
    );
    const candidates = [...first, ...this.nodes];
    const placed: Box[] = [];

    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.globalAlpha = 1;
    context.font = `${LABEL_FONT_PX}px ${colors.font}`;
    context.textAlign = "center";
    context.textBaseline = "top";
    context.lineJoin = "round";
    context.lineWidth = 3;
    for (const node of candidates) {
      if (placed.length >= MAX_LABELS) break;
      const x = node.x;
      const y = node.y;
      if (x < scene.left || x > scene.right || y < scene.top || y > scene.bottom) continue;
      const wanted =
        focus !== null || this.highlighted !== null || node.id === scene.peek
          ? isLit(node.id)
          : // Paper titles would bury the names: they show on hover and focus only.
            node.node.kind !== "paper" &&
            (node.rank < ALWAYS_LABELLED || node.radius * view.k >= threshold);
      if (!wanted) continue;

      const label = node.node.label;
      const text =
        label.length > MAX_LABEL_LENGTH ? `${label.slice(0, MAX_LABEL_LENGTH - 1)}…` : label;
      const screenX = x * view.k + view.x;
      const screenY = (y + node.radius) * view.k + view.y + 3;
      const halfWidth = context.measureText(text).width / 2 + 2;
      const box = {
        x0: screenX - halfWidth,
        y0: screenY,
        x1: screenX + halfWidth,
        y1: screenY + LABEL_FONT_PX + 2,
      };
      if (overlaps(box, placed)) continue;
      placed.push(box);
      context.strokeStyle = colors.halo;
      context.strokeText(text, screenX, screenY);
      context.fillStyle = colors.label;
      context.fillText(text, screenX, screenY);
    }
  }

  private toGraph(event: MouseEvent) {
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    return { x, y, gx: (x - this.view.x) / this.view.k, gy: (y - this.view.y) / this.view.k };
  }

  private nodeAt(gx: number, gy: number): SimNode | undefined {
    const tolerance = 4 / this.view.k;
    const minRadius = MIN_SCREEN_RADIUS_PX / this.view.k;
    let best: SimNode | undefined;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const node of this.nodes) {
      const dx = node.x - gx;
      const dy = node.y - gy;
      const distance = dx * dx + dy * dy;
      const reach = Math.max(node.radius, minRadius) + tolerance;
      if (distance <= reach * reach && distance < bestDistance) {
        best = node;
        bestDistance = distance;
      }
    }
    return best;
  }

  private onPointerDown(event: PointerEvent): void {
    const point = this.toGraph(event);
    this.pointers.set(event.pointerId, { x: point.x, y: point.y });
    this.canvas.setPointerCapture(event.pointerId);
    const fingers = [...this.pointers.values()];
    if (fingers.length === 2 && fingers[0] && fingers[1]) {
      // A second finger turns whatever the first one started into a pinch.
      this.endDrag();
      this.gesture = { kind: "pinch", from: [fingers[0], fingers[1]], view: { ...this.view } };
      return;
    }
    if (fingers.length > 2) return;
    const node = this.nodeAt(point.gx, point.gy);
    this.gesture = node
      ? { kind: "drag", node, startX: point.x, startY: point.y, moved: false }
      : {
          kind: "pan",
          startX: point.x,
          startY: point.y,
          viewX: this.view.x,
          viewY: this.view.y,
          moved: false,
        };
  }

  private onPointerMove(event: PointerEvent): void {
    const point = this.toGraph(event);
    if (this.pointers.has(event.pointerId))
      this.pointers.set(event.pointerId, { x: point.x, y: point.y });
    const gesture = this.gesture;
    if (gesture?.kind === "pinch") {
      const fingers = [...this.pointers.values()];
      if (fingers[0] && fingers[1]) {
        this.autoFit = false;
        this.followed = null;
        this.view = pinchView(gesture.view, gesture.from, [fingers[0], fingers[1]]);
        this.requestDraw();
      }
      return;
    }
    if (!gesture) {
      const node = this.nodeAt(point.gx, point.gy);
      if ((node?.id ?? null) !== this.hovered) {
        this.hovered = node?.id ?? null;
        this.canvas.style.cursor = node ? "pointer" : "";
        this.requestDraw();
      }
      return;
    }
    gesture.moved ||=
      Math.hypot(point.x - gesture.startX, point.y - gesture.startY) > CLICK_TOLERANCE_PX;
    if (!gesture.moved) return;
    this.autoFit = false;
    this.followed = null;
    if (gesture.kind === "drag") {
      // The dragged node follows the pointer at once; the layout moves the others around it.
      gesture.node.x = point.gx;
      gesture.node.y = point.gy;
      this.geometry++;
      this.send({
        type: "pin",
        index: this.nodes.indexOf(gesture.node),
        x: point.gx,
        y: point.gy,
        moving: !this.reducedMotion,
      });
      this.requestDraw();
    } else {
      this.view.x = gesture.viewX + point.x - gesture.startX;
      this.view.y = gesture.viewY + point.y - gesture.startY;
      this.canvas.style.cursor = "grabbing";
      this.requestDraw();
    }
  }

  private onPointerUp(event: PointerEvent): void {
    this.pointers.delete(event.pointerId);
    const gesture = this.gesture;
    if (gesture?.kind === "pinch") {
      // The finger left on the canvas starts nothing: lift it to pan or drag again.
      if (this.pointers.size === 0) this.gesture = null;
      return;
    }
    this.gesture = null;
    this.canvas.style.cursor = "";
    if (gesture?.kind === "drag") {
      if (gesture.moved) this.send({ type: "release", index: this.nodes.indexOf(gesture.node) });
      else this.select(gesture.node);
    } else if (gesture && !gesture.moved) {
      this.callbacks.onSelect(null);
    }
  }

  private onPointerLeave(): void {
    if (this.hovered !== null && !this.gesture) {
      this.hovered = null;
      this.requestDraw();
    }
  }

  private onDoubleClick(event: MouseEvent): void {
    const point = this.toGraph(event);
    const node = this.nodeAt(point.gx, point.gy);
    if (node) this.callbacks.onOpen(node.id);
  }

  /** Let a dragged node go, without selecting it. */
  private endDrag(): void {
    if (this.gesture?.kind === "drag" && this.gesture.moved) {
      this.send({ type: "release", index: this.nodes.indexOf(this.gesture.node) });
    }
    this.gesture = null;
  }

  private onWheel(event: WheelEvent): void {
    event.preventDefault();
    this.autoFit = false;
    this.followed = null;
    const point = this.toGraph(event);
    this.view = zoomAbout(this.view, point.x, point.y, Math.exp(-event.deltaY * 0.0015));
    this.requestDraw();
  }

  /** Select a node, panning it out from under an overlay if needed. */
  private select(node: SimNode): void {
    this.callbacks.onSelect(node.id);
    this.autoFit = false;
    this.followed = null;
    const screenX = node.x * this.view.k + this.view.x;
    const min = this.overlays.left + 24;
    const max = this.canvas.clientWidth - this.overlays.right - 24;
    if (screenX < min || screenX > max) {
      this.view.x += (min + max) / 2 - screenX;
      this.requestDraw();
    }
  }
}
