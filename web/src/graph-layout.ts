export interface Point {
  x: number;
  y: number;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
/** Typical distance between neighboring nodes when a component is first laid out. */
const SPACING = 20;
/** Free space kept around each component on the spiral. */
const MARGIN = 20;
/** How far from its placed neighbor a new node starts. */
const JITTER = 30;

function phyllotaxis(center: Point, index: number, spacing: number): Point {
  const radius = spacing * Math.sqrt(index + 0.5);
  const angle = index * GOLDEN_ANGLE;
  return { x: center.x + radius * Math.cos(angle), y: center.y + radius * Math.sin(angle) };
}

/** Connected components, each listed in breadth-first order from its best-connected node. */
function components(neighbors: readonly number[][]): number[][] {
  const seen = new Uint8Array(neighbors.length);
  const order = neighbors
    .map((adjacent, index) => [index, adjacent.length] as const)
    .sort((a, b) => b[1] - a[1]);
  const result: number[][] = [];
  for (const [start] of order) {
    if (seen[start]) continue;
    seen[start] = 1;
    const members = [start];
    for (let head = 0; head < members.length; head++) {
      for (const next of neighbors[members[head] ?? 0] ?? []) {
        if (!seen[next]) {
          seen[next] = 1;
          members.push(next);
        }
      }
    }
    result.push(members);
  }
  return result;
}

/**
 * Starting positions for the `count` nodes of a graph, given as index pairs in `links`.
 *
 * Nodes with a `known` position keep it; nodes linked to them start next to them. Each
 * component without any known node starts as a compact cluster, on a spiral around what is
 * already placed, biggest first. Starting components in one piece lets the force simulation
 * settle in a few dozen steps, instead of pulling co-authors together from opposite sides
 * of the graph (which never finishes for thousands of nodes).
 */
/** Whether each node belongs to the largest connected component of the graph. */
export function inLargestComponent(
  count: number,
  links: readonly (readonly [number, number])[],
): boolean[] {
  const neighbors = adjacency(count, links);
  const largest = components(neighbors).reduce<number[]>(
    (best, members) => (members.length > best.length ? members : best),
    [],
  );
  const result = new Array<boolean>(count).fill(false);
  for (const index of largest) result[index] = true;
  return result;
}

function adjacency(count: number, links: readonly (readonly [number, number])[]): number[][] {
  const neighbors: number[][] = Array.from({ length: count }, () => []);
  for (const [source, target] of links) {
    neighbors[source]?.push(target);
    neighbors[target]?.push(source);
  }
  return neighbors;
}

export function initialPositions(
  count: number,
  links: readonly (readonly [number, number])[],
  known: readonly (Point | undefined)[],
): Point[] {
  const neighbors = adjacency(count, links);
  const positions: (Point | undefined)[] = Array.from({ length: count }, (_, i) => known[i]);

  // Extent of what is already placed: new components go around it.
  let placed = 0;
  const center = { x: 0, y: 0 };
  for (const point of positions) {
    if (!point) continue;
    placed++;
    center.x += point.x;
    center.y += point.y;
  }
  if (placed > 0) {
    center.x /= placed;
    center.y /= placed;
  }
  let extent = 0;
  for (const point of positions) {
    if (point) extent = Math.max(extent, Math.hypot(point.x - center.x, point.y - center.y));
  }

  const fresh: number[][] = [];
  for (const members of components(neighbors)) {
    const anchors = members.filter((index) => positions[index]);
    if (anchors.length === 0) {
      fresh.push(members);
      continue;
    }
    // Grow outwards from the placed nodes, each new node next to a placed neighbor.
    const queue = [...anchors];
    for (let head = 0; head < queue.length; head++) {
      const from = positions[queue[head] ?? 0];
      for (const next of neighbors[queue[head] ?? 0] ?? []) {
        if (positions[next] || !from) continue;
        positions[next] = {
          x: from.x + (Math.random() - 0.5) * JITTER,
          y: from.y + (Math.random() - 0.5) * JITTER,
        };
        queue.push(next);
      }
    }
  }

  // Components go on a spiral where each one takes the area of its disc plus a margin, so
  // that they start side by side; a little randomness keeps the spiral from showing.
  fresh.sort((a, b) => b.length - a.length);
  let area = extent > 0 ? (extent + MARGIN) ** 2 : 0;
  for (const [index, members] of fresh.entries()) {
    const footprint = (SPACING * Math.sqrt(members.length) + MARGIN) ** 2;
    const distance = area === 0 ? 0 : Math.sqrt(area + footprint / 2);
    area += footprint;
    const angle = index * GOLDEN_ANGLE + (Math.random() - 0.5) * 0.4;
    const origin = {
      x: center.x + distance * Math.cos(angle),
      y: center.y + distance * Math.sin(angle),
    };
    for (const [rank, node] of members.entries()) {
      positions[node] = phyllotaxis(origin, rank, SPACING);
    }
  }

  return positions.map((point) => point ?? { x: center.x, y: center.y });
}
