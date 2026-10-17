import type { ComponentProps } from "preact";
import type { GraphView } from "./GraphView";
import { lazyView } from "./lazy-view";

/**
 * The graph view, its renderer and panels downloaded when the Graph tab is first opened
 * (PERF-13): about a third of the app's script, which the list never needs.
 */
export const LazyGraphView = lazyView<ComponentProps<typeof GraphView>>("graph", () =>
  import("./GraphView").then(({ GraphView }) => GraphView),
);
