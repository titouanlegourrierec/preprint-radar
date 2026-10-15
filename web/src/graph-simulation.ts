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
 * The cooling of a new graph (UX-30): no collisions and little friction, so that the layout
 * reaches its equilibrium at once, without Reheat. The former cooling (300 ticks with
 * collisions, friction 0.4) stopped short of it on a week of cs.CV (1,656 nodes): each
 * Reheat made the links shorter, by 19% after three. This one gets as far in one go, 530
 * ticks in about 3.6 s; friction 0.2 still left two Reheats' worth. Larger graphs get fewer
 * ticks, in proportion, down to `minTicks`, so that a layout takes about as long: a month
 * with its authors (10,234 nodes) got 82 ticks with friction 0.6, its links 70% longer.
 */
const COOLING = { ticks: 530, upTo: 2500, minTicks: 80, velocityDecay: 0.1 };
/**
 * A layout already at its equilibrium moving again (Reheat, new forces, a graph mostly
 * laid out already): d3's own decay and friction, so that it settles back without
 * scattering. Reheat from alpha 1 with the cooling's friction moved nodes by a third of the
 * graph's radius; from 0.5 with this one, by 4%, five times slower.
 */
const SETTLING = { alphaDecay: 0.0228, velocityDecay: 0.4 };
/** A short last pass with collisions, which part overlapping nodes and keeps the rest. */
const FINISH = { alpha: 0.1, alphaDecay: 0.05, velocityDecay: 0.4 };
/**
 * Above this alpha, a cooling is not shown (UX-30): the starting spiral bursts open, a frame
 * moving nodes by a third of the graph's final radius and the graph growing 1.6 times as
 * the view follows it. Below, frames move them by 1.8% at most (the former cooling, shown
 * from the start: 22%), and the graph has its size. It takes 0.5 s on a week of cs.CV.
 */
const HIDDEN_ABOVE_ALPHA = 0.3;
/** Ticks run at most to settle at once (reduced motion). */
const SETTLE_MAX_TICKS = 1000;
/**
 * How much harder nodes outside the largest component are pulled towards the center, once
 * that component is big: between these sizes, the extra pull grows from nothing to full.
 */
const SATELLITE_GRAVITY = 4;
const BIG_CORE = { from: 500, to: 2000 };
/** Alpha of a layout on the move, while a node is dragged. */
const DRAG_ALPHA_TARGET = 0.3;

/** The alpha decay that cools `nodes` nodes from alpha 1 to rest in the cooling's ticks. */
export function coolingDecay(nodes: number, alphaMin = 0.001): number {
  const ticks = Math.max(
    COOLING.minTicks,
    Math.min(COOLING.ticks, (COOLING.ticks * COOLING.upTo) / Math.max(1, nodes)),
  );
  return 1 - alphaMin ** (1 / ticks);
}

export class Layout {
  private readonly linkForce = forceLink<LayoutNode, LayoutLink>([]);
  private readonly chargeForce = forceManyBody<LayoutNode>();
  private readonly collideForce = forceCollide<LayoutNode>();
  private readonly xForce = forceX<LayoutNode>(0);
  private readonly yForce = forceY<LayoutNode>(0);
  private readonly simulation = forceSimulation<LayoutNode, LayoutLink>([]).stop();
  private nodes: LayoutNode[] = [];
  private settings: ForceSettings;
  /** Cooling to the equilibrium or settling back to it, then the short pass with collisions. */
  private phase: "cooling" | "settling" | "finish" = "cooling";

  constructor(settings: ForceSettings) {
    this.settings = settings;
    this.simulation
      .force("link", this.linkForce)
      .force("charge", this.chargeForce)
      .force("x", this.xForce)
      .force("y", this.yForce);
    this.applyForces();
  }

  /**
   * Lay out a new graph from its starting positions, at `alpha`: 1 cools a new graph to its
   * equilibrium, less settles one mostly laid out already.
   */
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
    this.phase = alpha >= 1 ? "cooling" : "settling";
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

  /**
   * Make the layout move again, at least at `alpha` (Reheat, new forces): it settles back to
   * its equilibrium. A layout still cooling more than that goes on cooling.
   */
  heat(alpha: number): void {
    if (alpha <= this.simulation.alpha()) return;
    this.phase = "settling";
    this.applyPhase();
    this.simulation.alpha(alpha);
  }

  /** Hold a node at a point, as while it is dragged; `moving` keeps the layout warm. */
  pin(index: number, x: number, y: number, moving: boolean): void {
    const node = this.nodes[index];
    if (!node) return;
    node.fx = x;
    node.fy = y;
    if (moving) {
      // Warms up from where it is, as d3's restart does: the layout eases into motion. A
      // layout at rest moves as its last pass does (collisions, quick to settle); one still
      // cooling goes on cooling.
      if (!this.running) {
        this.phase = "finish";
        this.applyPhase();
      }
      this.simulation.alphaTarget(DRAG_ALPHA_TARGET);
      this.simulation.alpha(Math.max(this.simulation.alpha(), 2 * this.simulation.alphaMin()));
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

  /** Whether the layout cools through its violent start, which is not shown. */
  get hidden(): boolean {
    return this.phase === "cooling" && this.simulation.alpha() > HIDDEN_ABOVE_ALPHA;
  }

  /** Whether the layout still moves. */
  get running(): boolean {
    return this.simulation.alpha() >= this.simulation.alphaMin();
  }

  /** One step of the layout; whether it still moves after it. */
  step(): boolean {
    if (!this.running) return false;
    this.simulation.tick();
    // At rest, the last pass parts overlapping nodes (a large graph has no collisions).
    if (!this.running && this.phase !== "finish" && this.nodes.length <= LARGE_GRAPH) {
      this.phase = "finish";
      this.applyPhase();
      this.simulation.alpha(FINISH.alpha);
    }
    return this.running;
  }

  /** Run the layout to rest at once (reduced motion): the cooling and its last pass. */
  settle(): void {
    for (let tick = 0; tick < SETTLE_MAX_TICKS && this.step(); tick++);
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
    // approximation and no collisions. Never cap the repulsion distance (`distanceMax`)
    // nor make `theta` much coarser: nodes would pile up in rings at the cutoff distance
    // around each quadrant.
    const large = this.nodes.length > LARGE_GRAPH;
    this.chargeForce
      .strength((node) => -settings.repelForce * (5 + node.radius))
      .theta(large ? 1.2 : 0.9);
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
    this.applyPhase();
  }

  /** The phase's decay, friction and collisions. */
  private applyPhase(): void {
    const { phase } = this;
    const collide = phase === "finish" && this.nodes.length <= LARGE_GRAPH;
    this.simulation.force("collide", collide ? this.collideForce : null);
    if (phase === "cooling") {
      this.simulation
        .alphaDecay(coolingDecay(this.nodes.length))
        .velocityDecay(COOLING.velocityDecay);
    } else {
      const { alphaDecay, velocityDecay } = phase === "finish" ? FINISH : SETTLING;
      this.simulation.alphaDecay(alphaDecay).velocityDecay(velocityDecay);
    }
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
