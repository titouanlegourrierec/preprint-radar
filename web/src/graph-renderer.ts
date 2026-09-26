import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { Graph, GraphNode } from "./graph";
import { initialPositions, inLargestComponent } from "./graph-layout";

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
  /** On-screen size from which nodes get a label, as a multiple of the default. */
  labelThreshold: number;
}

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

interface SimNode extends SimulationNodeDatum {
  id: string;
  node: GraphNode;
  /** Position among the nodes of the same kind, biggest first. */
  rank: number;
  /** Radius before the node size setting is applied. */
  baseRadius: number;
  radius: number;
  degree: number;
  /** Whether the node belongs to the largest connected component. */
  main: boolean;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  source: SimNode;
  target: SimNode;
  weight: number;
}

type Gesture =
  | { kind: "drag"; node: SimNode; startX: number; startY: number; moved: boolean }
  | { kind: "pan"; startX: number; startY: number; viewX: number; viewY: number; moved: boolean };

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
/**
 * How much harder nodes outside the largest component are pulled towards the center, once
 * that component is big: between these sizes, the extra pull grows from nothing to full.
 */
const SATELLITE_GRAVITY = 4;
const BIG_CORE = { from: 500, to: 2000 };
/** Above this many nodes, the simulation trades accuracy for speed. */
const LARGE_GRAPH = 2000;
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

/**
 * Radius of a node with `papers` papers. The area grows with the paper count, on the same
 * scale whatever the graph, so that a node with one paper stays small.
 */
export function nodeRadius(papers: number): number {
  return Math.min(MAX_RADIUS, 2.5 + 3.5 * Math.sqrt(Math.max(0, papers - 1)));
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

function readColors() {
  const style = getComputedStyle(document.documentElement);
  const value = (name: string) => style.getPropertyValue(name).trim();
  return {
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
  private readonly linkForce = forceLink<SimNode, SimLink>([]);
  private readonly chargeForce = forceManyBody<SimNode>();
  private readonly collideForce = forceCollide<SimNode>();
  private readonly xForce = forceX<SimNode>(0);
  private readonly yForce = forceY<SimNode>(0);
  private readonly simulation = forceSimulation<SimNode, SimLink>([]);
  private nodes: SimNode[] = [];
  private links: SimLink[] = [];
  private byId = new Map<string, SimNode>();
  private neighbors = new Map<string, Set<string>>();
  /** Last known position of every node seen so far, reused when the graph changes. */
  private readonly positions = new Map<string, { x: number; y: number }>();
  private view: View = { x: 0, y: 0, k: 1 };
  /** Keep the whole graph in view until the user pans or zooms. */
  private autoFit = true;
  private overlays: Overlays = { left: 0, right: 0 };
  private hovered: string | null = null;
  private selected: string | null = null;
  private highlighted: ReadonlySet<string> | null = null;
  private colors = readColors();
  private gesture: Gesture | null = null;
  private frame = 0;
  private readonly reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  private readonly cleanups: (() => void)[] = [];

  constructor(canvas: HTMLCanvasElement, callbacks: RendererCallbacks, settings: RendererSettings) {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("This browser cannot draw on a canvas.");
    this.canvas = canvas;
    this.context = context;
    this.callbacks = callbacks;
    this.settings = settings;

    this.simulation
      .force("link", this.linkForce)
      .force("charge", this.chargeForce)
      .force("collide", this.collideForce)
      .force("x", this.xForce)
      .force("y", this.yForce)
      .on("tick", () => {
        if (this.autoFit) this.fitNow();
        this.requestDraw();
      })
      .on("end", () => this.savePositions())
      .stop();
    this.applyForces();

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
      this.listen("pointerup", () => this.onPointerUp()),
      this.listen("pointercancel", () => this.onPointerUp()),
      this.listen("pointerleave", () => this.onPointerLeave()),
      this.listen("dblclick", (event) => this.onDoubleClick(event)),
      this.listen("wheel", (event) => this.onWheel(event), { passive: false }),
    );
    this.resize();
  }

  /** Show a new graph, keeping the position of the nodes that were already there. */
  setGraph(graph: Graph): void {
    this.savePositions();
    const degree = new Map<string, number>();
    const ranks = { institution: 0, author: 0 };
    for (const link of graph.links) {
      degree.set(link.source, (degree.get(link.source) ?? 0) + 1);
      degree.set(link.target, (degree.get(link.target) ?? 0) + 1);
    }

    this.nodes = graph.nodes.map((node) => {
      const baseRadius = nodeRadius(node.paperIds.length);
      return {
        id: node.id,
        node,
        rank: ranks[node.kind]++,
        baseRadius,
        radius: baseRadius * this.settings.nodeSize,
        degree: degree.get(node.id) ?? 0,
        main: false,
      };
    });
    this.byId = new Map(this.nodes.map((node) => [node.id, node]));
    this.neighbors = new Map(this.nodes.map((node) => [node.id, new Set<string>()]));
    this.links = [];
    for (const link of graph.links) {
      const source = this.byId.get(link.source);
      const target = this.byId.get(link.target);
      if (!source || !target) continue;
      this.links.push({ source, target, weight: link.weight });
      this.neighbors.get(source.id)?.add(target.id);
      this.neighbors.get(target.id)?.add(source.id);
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
      node.main = main[index] ?? false;
    }

    // A mostly new graph (other papers, authors turned on) is framed again from scratch.
    if (known < this.nodes.length / 2) this.autoFit = true;
    this.simulation.nodes(this.nodes);
    this.linkForce.links(this.links);
    this.applyForces();
    if (this.reducedMotion) {
      this.simulation.stop().tick(this.nodes.length > LARGE_GRAPH ? 60 : 300);
      this.savePositions();
      if (this.autoFit) this.fitNow();
      this.requestDraw();
    } else {
      this.simulation.alpha(known === 0 ? 1 : 0.4).restart();
    }
  }

  setSettings(settings: RendererSettings): void {
    const previous = this.settings;
    this.settings = settings;
    if (settings.nodeSize !== previous.nodeSize) {
      for (const node of this.nodes) node.radius = node.baseRadius * settings.nodeSize;
    }
    const forcesChanged =
      settings.centerForce !== previous.centerForce ||
      settings.repelForce !== previous.repelForce ||
      settings.linkForce !== previous.linkForce ||
      settings.linkDistance !== previous.linkDistance ||
      settings.nodeSize !== previous.nodeSize;
    if (forcesChanged) {
      this.applyForces();
      if (this.nodes.length > 0) this.reheat(0.3);
    }
    this.requestDraw();
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
    const width = this.canvas.clientWidth;
    const k = Math.max(this.view.k, FOCUS_ZOOM);
    const center = (this.overlays.left + width - this.overlays.right) / 2;
    this.view = {
      k,
      x: center - (node.x ?? 0) * k,
      y: this.canvas.clientHeight / 2 - (node.y ?? 0) * k,
    };
    this.autoFit = false;
    this.requestDraw();
  }

  /** Zoom to show the whole graph, and keep it in view while the layout settles. */
  fit(): void {
    this.autoFit = true;
    this.fitNow();
    this.requestDraw();
  }

  /** Restart the layout, e.g. to escape a tangled state. */
  reheat(alpha = 1): void {
    if (this.reducedMotion) return;
    this.simulation.alpha(Math.max(this.simulation.alpha(), alpha)).restart();
  }

  destroy(): void {
    this.simulation.stop();
    cancelAnimationFrame(this.frame);
    for (const cleanup of this.cleanups) cleanup();
  }

  private listen<K extends keyof HTMLElementEventMap>(
    type: K,
    handler: (event: HTMLElementEventMap[K]) => void,
    options?: AddEventListenerOptions,
  ): () => void {
    this.canvas.addEventListener(type, handler, options);
    return () => this.canvas.removeEventListener(type, handler, options);
  }

  private applyForces(): void {
    const { settings } = this;
    // Big graphs (e.g. every author of a month of papers) get a coarser Barnes-Hut
    // approximation, no collisions and a shorter cooling. Never cap the repulsion distance
    // (`distanceMax`) nor make `theta` much coarser: nodes would pile up in rings at the
    // cutoff distance around each quadrant.
    const large = this.nodes.length > LARGE_GRAPH;
    this.chargeForce
      .strength((node) => -settings.repelForce * (5 + node.radius))
      .theta(large ? 1.2 : 0.9);
    this.simulation.force("collide", large ? null : this.collideForce);
    this.linkForce
      .distance((link) => settings.linkDistance + link.source.radius + link.target.radius)
      // Links of well-connected nodes are softer, so that hubs do not collapse their
      // neighborhood (d3's default strength follows the same idea).
      .strength(
        (link) =>
          settings.linkForce *
          Math.min(
            1,
            (0.5 + 0.25 * link.weight) / Math.min(link.source.degree, link.target.degree),
          ),
      );
    this.collideForce.radius((node) => node.radius + 2).iterations(2);
    // Small components are pulled harder towards the center when the largest component is
    // big: its links keep it compact while its repulsion holds them in a ring far around it.
    // (With a small core, the same pull would push the core aside instead.)
    const core = this.nodes.filter((node) => node.main).length;
    const ramp = Math.min(1, Math.max(0, (core - BIG_CORE.from) / (BIG_CORE.to - BIG_CORE.from)));
    const boost = 1 + (SATELLITE_GRAVITY - 1) * ramp;
    const gravity = (node: SimNode) => 0.2 * settings.centerForce * (node.main ? 1 : boost);
    this.xForce.strength(gravity);
    this.yForce.strength(gravity);
    this.simulation.alphaDecay(large ? 0.08 : 0.0228).velocityDecay(large ? 0.6 : 0.4);
  }

  private savePositions(): void {
    for (const node of this.nodes) {
      if (node.x !== undefined && node.y !== undefined) {
        this.positions.set(node.id, { x: node.x, y: node.y });
      }
    }
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
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      bounds.minX = Math.min(bounds.minX, x - node.radius);
      bounds.minY = Math.min(bounds.minY, y - node.radius);
      bounds.maxX = Math.max(bounds.maxX, x + node.radius);
      bounds.maxY = Math.max(bounds.maxY, y + node.radius);
    }
    return bounds;
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
    const isLit = (id: string): boolean =>
      focus !== null
        ? id === focus || near?.has(id) === true
        : highlighted === null || highlighted.has(id);
    const dimmed = focus !== null || highlighted !== null;

    context.setTransform(ratio * view.k, 0, 0, ratio * view.k, ratio * view.x, ratio * view.y);

    // Links, batched by style: a handful of strokes per frame.
    const thin = new Path2D();
    const medium = new Path2D();
    const thick = new Path2D();
    const focused = new Path2D();
    for (const { source, target, weight } of this.links) {
      const sx = source.x ?? 0;
      const sy = source.y ?? 0;
      const tx = target.x ?? 0;
      const ty = target.y ?? 0;
      if (
        (sx < left && tx < left) ||
        (sx > right && tx > right) ||
        (sy < top && ty < top) ||
        (sy > bottom && ty > bottom)
      ) {
        continue;
      }
      const path =
        focus !== null && (source.id === focus || target.id === focus)
          ? focused
          : weight >= 3
            ? thick
            : weight === 2
              ? medium
              : thin;
      path.moveTo(sx, sy);
      path.lineTo(tx, ty);
    }
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
      context.globalAlpha = 0.9;
      context.strokeStyle = colors.accent;
      context.lineWidth = 1.4 / view.k;
      context.stroke(focused);
    }

    // Nodes, batched by color and emphasis.
    const shapes = {
      institution: { lit: new Path2D(), dim: new Path2D() },
      author: { lit: new Path2D(), dim: new Path2D() },
    };
    const rings = new Path2D();
    const ringGap = 2 / view.k;
    const minRadius = MIN_SCREEN_RADIUS_PX / view.k;
    for (const node of this.nodes) {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const r = Math.max(node.radius, minRadius);
      if (x + r < left || x - r > right || y + r < top || y - r > bottom) continue;
      const path = shapes[node.node.kind][isLit(node.id) ? "lit" : "dim"];
      path.moveTo(x + r, y);
      path.arc(x, y, r, 0, 2 * Math.PI);
      if (node.id === this.selected || (focus === null && highlighted?.has(node.id) === true)) {
        rings.moveTo(x + r + ringGap, y);
        rings.arc(x, y, r + ringGap, 0, 2 * Math.PI);
      }
    }
    for (const kind of ["institution", "author"] as const) {
      context.fillStyle = colors[kind];
      context.globalAlpha = 0.15;
      context.fill(shapes[kind].dim);
      context.globalAlpha = 1;
      context.fill(shapes[kind].lit);
    }
    context.strokeStyle = colors.accent;
    context.lineWidth = 2 / view.k;
    context.stroke(rings);

    this.drawLabels({ left, top, right, bottom, focus, isLit });
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
    isLit: (id: string) => boolean;
  }): void {
    const { context, view, colors } = this;
    const { focus, isLit } = scene;
    const ratio = window.devicePixelRatio || 1;
    const threshold = LABEL_RADIUS_PX * this.settings.labelThreshold;
    const focusNode = focus === null ? undefined : this.byId.get(focus);
    const candidates = focusNode ? [focusNode, ...this.nodes] : this.nodes;
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
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      if (x < scene.left || x > scene.right || y < scene.top || y > scene.bottom) continue;
      const wanted =
        focus !== null || this.highlighted !== null
          ? isLit(node.id)
          : node.rank < ALWAYS_LABELLED || node.radius * view.k >= threshold;
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
      const dx = (node.x ?? 0) - gx;
      const dy = (node.y ?? 0) - gy;
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
    const node = this.nodeAt(point.gx, point.gy);
    this.canvas.setPointerCapture(event.pointerId);
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
    const gesture = this.gesture;
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
    if (gesture.kind === "drag") {
      gesture.node.fx = point.gx;
      gesture.node.fy = point.gy;
      if (this.reducedMotion) {
        gesture.node.x = point.gx;
        gesture.node.y = point.gy;
        this.requestDraw();
      } else {
        this.simulation.alphaTarget(0.3).restart();
      }
    } else {
      this.view.x = gesture.viewX + point.x - gesture.startX;
      this.view.y = gesture.viewY + point.y - gesture.startY;
      this.canvas.style.cursor = "grabbing";
      this.requestDraw();
    }
  }

  private onPointerUp(): void {
    const gesture = this.gesture;
    this.gesture = null;
    this.canvas.style.cursor = "";
    if (gesture?.kind === "drag") {
      gesture.node.fx = null;
      gesture.node.fy = null;
      this.simulation.alphaTarget(0);
      if (!gesture.moved) this.select(gesture.node);
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

  private onWheel(event: WheelEvent): void {
    event.preventDefault();
    this.autoFit = false;
    const point = this.toGraph(event);
    const k = Math.min(
      MAX_ZOOM,
      Math.max(MIN_ZOOM, this.view.k * Math.exp(-event.deltaY * 0.0015)),
    );
    this.view = { k, x: point.x - point.gx * k, y: point.y - point.gy * k };
    this.requestDraw();
  }

  /** Select a node, panning it out from under an overlay if needed. */
  private select(node: SimNode): void {
    this.callbacks.onSelect(node.id);
    this.autoFit = false;
    const screenX = (node.x ?? 0) * this.view.k + this.view.x;
    const min = this.overlays.left + 24;
    const max = this.canvas.clientWidth - this.overlays.right - 24;
    if (screenX < min || screenX > max) {
      this.view.x += (min + max) / 2 - screenX;
      this.requestDraw();
    }
  }
}
