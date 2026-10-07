import { categoryName } from "../format";
import type { ThemePreference } from "../preferences";
import type { ViewState } from "../url-state";

const THEME_ICONS: Record<ThemePreference, string> = { auto: "◐", light: "☀", dark: "☾" };

/** A tab's link: its address, whether it is the current view, and its plain click. */
export type TabLink = (
  active: boolean,
  patch: Partial<ViewState>,
) => {
  href: string;
  "aria-current": "page" | undefined;
  onClick: (event: MouseEvent) => void;
};

interface Props {
  view: ViewState["view"];
  category: string | undefined;
  /** The day of the store's last update, as shown. */
  lastUpdate: string | null;
  readingListSize: number;
  /** The archive's years the highly cited view shows, which the graph and Rankings take. */
  archiveRange: ViewState["year"];
  tab: TabLink;
  theme: ThemePreference;
  nextTheme: ThemePreference;
  onTheme: () => void;
}

/** The site's name, its views as tabs, and the theme switch. */
export function Topbar(props: Props) {
  const { view, tab } = props;
  const cited = view === "cited";
  return (
    <header class="topbar">
      <div class="topbar__brand">
        <h1>Preprint Radar</h1>
        {props.category && <span class="topbar__category">{categoryName(props.category)}</span>}
        {props.lastUpdate && <span class="muted">Updated {props.lastUpdate}</span>}
      </div>
      <div class="topbar__tools">
        <nav class="tabs" aria-label="Views">
          <a
            class={`tab${view === "papers" ? " tab--active" : ""}`}
            {...tab(view === "papers", { view: "papers", year: null })}
          >
            Papers
          </a>
          <a
            class={`tab${cited ? " tab--active" : ""}`}
            title="The most cited papers older than a year, by year of first version"
            {...tab(cited, { view: "cited" })}
          >
            Highly cited
          </a>
          <a
            class={`tab${view === "graph" ? " tab--active" : ""}`}
            // From the highly cited papers, the graph shows them.
            {...tab(view === "graph", {
              view: "graph",
              ...(cited ? { year: props.archiveRange } : {}),
            })}
          >
            Graph
          </a>
          <a
            class={`tab${view === "rankings" ? " tab--active" : ""}`}
            title="Institutions and authors of the papers shown, by papers or citations"
            {...tab(view === "rankings", {
              view: "rankings",
              ...(cited ? { year: props.archiveRange } : {}),
            })}
          >
            Rankings
          </a>
          <a
            class={`tab${view === "reading-list" ? " tab--active" : ""}`}
            {...tab(view === "reading-list", { view: "reading-list" })}
          >
            Reading list ({props.readingListSize.toLocaleString()})
          </a>
          <a
            class={`tab${view === "about" ? " tab--active" : ""}`}
            title="Where the data comes from, corrections and privacy"
            {...tab(view === "about", { view: "about" })}
          >
            About
          </a>
        </nav>
        <button
          type="button"
          class="icon-button"
          title={`Theme: ${props.theme} — click for ${props.nextTheme}`}
          aria-label={`Theme: ${props.theme}. Switch to ${props.nextTheme}.`}
          onClick={props.onTheme}
        >
          {THEME_ICONS[props.theme]}
        </button>
      </div>
    </header>
  );
}
