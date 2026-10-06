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

/**
 * The force layout of the graph, without a DOM: `graph-worker.ts` runs it off the main
 * thread, so that a graph of tens of thousands of nodes never freezes the page (PERF-2).
 * It ticks only when asked ({@link Layout.step}); positions go out as a flat array.
 */

/** Forces chosen in the graph settings panel. */
export interface ForceSettings {
  /** Pull towards the center, from 0 to 1. */
  centerForce: number;
  /** Repulsion between nodes. */
  repelForce: number;
  /** Stiffness of links, as a multiple of the default. */
  linkForce: number;
  /** Rest length of links between node borders, in graph units. */
  linkDistance: number;
}

/** What the layout needs of the graph: nodes by index, links between indices. */
export interface LayoutGraph {
  /** Starting positions, x then y for each node. */
  positions: Float32Array;
  radii: Float32Array;
  degrees: Uint32Array;
  /** 1 for nodes of the largest connected component. */
  main: Uint8Array;
  /** Source then target index for each link. */
  links: Uint32Array;
  weights: Float32Array;
}

interface LayoutNode extends SimulationNodeDatum {
  radius: number;
  degree: number;
  main: boolean;
}

interface LayoutLink extends SimulationLinkDatum<LayoutNode> {
  source: LayoutNode;
  target: LayoutNode;
  weight: number;
}

/** Above this many nodes, the simulation trades accuracy for speed. */
export const LARGE_GRAPH = 2000;
/**
 * How much harder nodes outside the largest component are pulled towards the center, once
 * that component is big: between these sizes, the extra pull grows from nothing to full.
 */
const SATELLITE_GRAVITY = 4;
const BIG_CORE = { from: 500, to: 2000 };
/** Ticks run at once under reduced motion: the layout appears settled, without moving. */
const SETTLE_TICKS = { small: 300, large: 60 };
/** Alpha of a layout on the move, while a node is dragged. */
const DRAG_ALPHA_TARGET = 0.3;

export class Layout {
  private readonly linkForce = forceLink<LayoutNode, LayoutLink>([]);
  private readonly chargeForce = forceManyBody<LayoutNode>();
  private readonly collideForce = forceCollide<LayoutNode>();
  private readonly xForce = forceX<LayoutNode>(0);
  private readonly yForce = forceY<LayoutNode>(0);
  private readonly simulation = forceSimulation<LayoutNode, LayoutLink>([]).stop();
  private nodes: LayoutNode[] = [];
  private settings: ForceSettings;

  constructor(settings: ForceSettings) {
    this.settings = settings;
    this.simulation
      .force("link", this.linkForce)
      .force("charge", this.chargeForce)
      .force("x", this.xForce)
      .force("y", this.yForce);
    this.applyForces();
  }

  /** Lay out a new graph from its starting positions, at `alpha` (1 for a new graph). */
  setGraph(graph: LayoutGraph, alpha: number): void {
    this.nodes = Array.from(graph.radii, (radius, index) => ({
      index,
      radius,
      degree: graph.degrees[index] ?? 0,
      main: graph.main[index] === 1,
      x: graph.positions[2 * index] ?? 0,
      y: graph.positions[2 * index + 1] ?? 0,
    }));
    const links: LayoutLink[] = [];
    for (let link = 0; 2 * link + 1 < graph.links.length; link++) {
      const source = this.nodes[graph.links[2 * link] ?? -1];
      const target = this.nodes[graph.links[2 * link + 1] ?? -1];
      if (source && target) links.push({ source, target, weight: graph.weights[link] ?? 1 });
    }
    this.simulation.nodes(this.nodes);
    this.linkForce.links(links);
    this.applyForces();
    this.simulation.alpha(alpha).alphaTarget(0);
  }

  /** New forces, and node radii when node sizes changed. */
  setForces(settings: ForceSettings, radii?: Float32Array): void {
    this.settings = settings;
    if (radii) {
      for (const node of this.nodes) node.radius = radii[node.index ?? 0] ?? node.radius;
    }
    this.applyForces();
  }

  /** Make the layout move again, at least at `alpha`. */
  heat(alpha: number): void {
    this.simulation.alpha(Math.max(this.simulation.alpha(), alpha));
  }

  /** Hold a node at a point, as while it is dragged; `moving` keeps the layout warm. */
  pin(index: number, x: number, y: number, moving: boolean): void {
    const node = this.nodes[index];
    if (!node) return;
    node.fx = x;
    node.fy = y;
    if (moving) {
      // Warms up from where it is, as d3's restart does: the layout eases into motion.
      this.simulation.alphaTarget(DRAG_ALPHA_TARGET);
      this.heat(2 * this.simulation.alphaMin());
    } else {
      node.x = x;
      node.y = y;
    }
  }

  /** Let a pinned node go, and the layout cool down. */
  release(index: number): void {
    const node = this.nodes[index];
    if (node) {
      node.fx = null;
      node.fy = null;
    }
    this.simulation.alphaTarget(0);
  }

  /** Whether the layout still moves. */
  get running(): boolean {
    return this.simulation.alpha() >= this.simulation.alphaMin();
  }

  /** One step of the layout; whether it still moves after it. */
  step(): boolean {
    if (!this.running) return false;
    this.simulation.tick();
    return this.running;
  }

  /** Run the layout to rest at once (reduced motion): fewer ticks for a large graph. */
  settle(): void {
    const large = this.nodes.length > LARGE_GRAPH;
    this.simulation.tick(large ? SETTLE_TICKS.large : SETTLE_TICKS.small);
    this.simulation.alpha(0);
  }

  /** Positions, x then y for each node. */
  positions(): Float32Array {
    const positions = new Float32Array(2 * this.nodes.length);
    for (const [index, node] of this.nodes.entries()) {
      positions[2 * index] = node.x ?? 0;
      positions[2 * index + 1] = node.y ?? 0;
    }
    return positions;
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
    const gravity = (node: LayoutNode) => 0.2 * settings.centerForce * (node.main ? 1 : boost);
    this.xForce.strength(gravity);
    this.yForce.strength(gravity);
    this.simulation.alphaDecay(large ? 0.08 : 0.0228).velocityDecay(large ? 0.6 : 0.4);
  }
}

/** A message to the layout worker. Typed arrays are transferred, not copied. */
export type ToLayout =
  | {
      type: "graph";
      /** Tells the positions of this graph from those of the graphs before it. */
      generation: number;
      graph: LayoutGraph;
      settings: ForceSettings;
      alpha: number;
      /** Run to rest at once (reduced motion) instead of moving. */
      settle: boolean;
    }
  | {
      type: "forces";
      settings: ForceSettings;
      radii?: Float32Array;
      alpha: number;
      settle: boolean;
    }
  | { type: "heat"; alpha: number; settle: boolean }
  | { type: "pin"; index: number; x: number; y: number; moving: boolean }
  | { type: "release"; index: number };

/** Positions from the layout worker, x then y for each node of graph `generation`. */
export interface FromLayout {
  generation: number;
  positions: Float32Array;
  /** Whether more positions follow; `false` once the layout is at rest. */
  moving: boolean;
}
