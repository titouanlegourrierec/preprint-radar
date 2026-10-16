import type { ComponentProps, FunctionComponent } from "preact";
import { useEffect, useState } from "preact/hooks";
import type { WorldMap } from "./WorldMap";

type Props = ComponentProps<typeof WorldMap>;

/** The map once its chunk loaded, for the next times Rankings shows countries. */
let loaded: FunctionComponent<Props> | null = null;

/**
 * Rankings' world map (UX-41), with its shapes and projection, downloaded when Rankings
 * first shows countries: the lists never need it.
 */
export function LazyWorldMap(props: Props) {
  const [View, setView] = useState(() => loaded);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (View !== null) return;
    let live = true;
    import("./WorldMap")
      .then(({ WorldMap }) => {
        loaded = WorldMap;
        if (live) setView(() => WorldMap);
      })
      .catch((error: unknown) => {
        console.warn("Could not load the map", error);
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [View]);
  if (View !== null) return <View {...props} />;
  return failed ? (
    <p class="notice notice--error" role="alert">
      The map could not be loaded: the site may have been updated meanwhile.{" "}
      <button type="button" class="link-button" onClick={() => window.location.reload()}>
        Reload
      </button>
    </p>
  ) : (
    <p class="notice" role="status">
      Loading the map…
    </p>
  );
}
