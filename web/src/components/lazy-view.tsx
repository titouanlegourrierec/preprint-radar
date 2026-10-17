import type { FunctionComponent } from "preact";
import { useEffect, useState } from "preact/hooks";

/**
 * A view downloaded when it is first shown, which the landing page never loads (PERF-13,
 * PERF-15): its chunk is asked for once for the page, a notice standing in meanwhile (none
 * when `quiet`, for a small part of a view), and Reload when it fails, the site having
 * been updated meanwhile, so that the old chunk is gone.
 *
 * @param what What the view shows, as the notices name it: "graph" ("Loading the graph…").
 */
export function lazyView<Props extends object>(
  what: string,
  load: () => Promise<FunctionComponent<Props>>,
  { quiet = false }: { quiet?: boolean } = {},
): FunctionComponent<Props> {
  // The view once its chunk loaded, for the next times it is shown.
  let loaded: FunctionComponent<Props> | null = null;
  return function LazyView(props: Props) {
    const [View, setView] = useState(() => loaded);
    const [failed, setFailed] = useState(false);
    useEffect(() => {
      if (View !== null) return;
      let live = true;
      load()
        .then((view) => {
          loaded = view;
          if (live) setView(() => view);
        })
        .catch((error: unknown) => {
          console.warn(`Could not load the ${what}`, error);
          if (live) setFailed(true);
        });
      return () => {
        live = false;
      };
    }, [View]);
    if (View !== null) return <View {...props} />;
    if (failed) {
      return (
        <p class="notice notice--error" role="alert">
          The {what} could not be loaded: the site may have been updated meanwhile.{" "}
          <button type="button" class="link-button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </p>
      );
    }
    return quiet ? null : (
      <p class="notice" role="status">
        Loading the {what}…
      </p>
    );
  };
}
