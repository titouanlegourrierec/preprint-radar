import type { ComponentProps, FunctionComponent } from "preact";
import { useEffect, useState } from "preact/hooks";
import type { GraphView } from "./GraphView";

type Props = ComponentProps<typeof GraphView>;

/** The graph's view once its chunk loaded, for the next visits of the tab. */
let loaded: FunctionComponent<Props> | null = null;

/**
 * The graph view, its renderer and panels downloaded when the Graph tab is first opened
 * (PERF-13): about a third of the app's script, which the list never needs.
 */
export function LazyGraphView(props: Props) {
  const [View, setView] = useState(() => loaded);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (View !== null) return;
    let live = true;
    import("./GraphView")
      .then(({ GraphView }) => {
        loaded = GraphView;
        if (live) setView(() => GraphView);
      })
      .catch((error: unknown) => {
        console.warn("Could not load the graph", error);
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [View]);
  if (View !== null) return <View {...props} />;
  return failed ? (
    <p class="notice notice--error" role="alert">
      The graph could not be loaded: the site may have been updated meanwhile.{" "}
      <button type="button" class="link-button" onClick={() => window.location.reload()}>
        Reload
      </button>
    </p>
  ) : (
    <p class="notice" role="status">
      Loading the graph…
    </p>
  );
}
