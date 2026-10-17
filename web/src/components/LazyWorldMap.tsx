import type { ComponentProps } from "preact";
import { lazyView } from "./lazy-view";
import type { WorldMap } from "./WorldMap";

/**
 * Rankings' world map (UX-41), with its shapes and projection, downloaded when Rankings
 * first shows countries: the lists never need it.
 */
export const LazyWorldMap = lazyView<ComponentProps<typeof WorldMap>>("map", () =>
  import("./WorldMap").then(({ WorldMap }) => WorldMap),
);
