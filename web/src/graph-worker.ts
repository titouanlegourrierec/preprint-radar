import { type FromLayout, Layout, type ToLayout } from "./graph-simulation";

/**
 * Runs the graph layout off the main thread (PERF-2): it ticks as fast as it can and posts
 * positions at most once a frame, while the page draws the latest ones and stays responsive.
 */

/** Ticks run between two posts, for at most this long. */
const POST_EVERY_MS = 16;

let layout: Layout | null = null;
let generation = 0;
let scheduled = false;

function post(moving: boolean): void {
  if (!layout) return;
  const positions = layout.positions();
  const message: FromLayout = { generation, positions, moving };
  self.postMessage(message, { transfer: [positions.buffer] });
}

function run(): void {
  scheduled = false;
  if (!layout) return;
  const start = performance.now();
  let moving = layout.running;
  while (moving && performance.now() - start < POST_EVERY_MS) moving = layout.step();
  post(moving);
  if (moving) schedule();
}

/** Tick on a later task, so that the messages that came in meanwhile are read first. */
function schedule(): void {
  if (scheduled) return;
  scheduled = true;
  setTimeout(run, 0);
}

function move(settle: boolean): void {
  if (!layout) return;
  if (settle) {
    layout.settle();
    post(false);
  } else {
    schedule();
  }
}

self.addEventListener("message", (event: MessageEvent<ToLayout>) => {
  const message = event.data;
  switch (message.type) {
    case "graph":
      layout ??= new Layout(message.settings);
      generation = message.generation;
      layout.setForces(message.settings);
      layout.setGraph(message.graph, message.alpha);
      move(message.settle);
      break;
    case "forces":
      layout?.setForces(message.settings, message.radii);
      layout?.heat(message.alpha);
      move(message.settle);
      break;
    case "heat":
      layout?.heat(message.alpha);
      move(message.settle);
      break;
    case "pin":
      layout?.pin(message.index, message.x, message.y, message.moving);
      if (message.moving) schedule();
      break;
    case "release":
      layout?.release(message.index);
      schedule();
      break;
  }
});
