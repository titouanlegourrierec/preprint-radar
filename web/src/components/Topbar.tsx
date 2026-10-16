import type { JSX } from "preact";
import type { ThemePreference } from "../preferences";
import { DEFAULT_STATE, type ViewState } from "../url-state";
import {
  AutoThemeIcon,
  CitedIcon,
  GraphIcon,
  InfoIcon,
  MoonIcon,
  PapersIcon,
  RankingsIcon,
  StarIcon,
  SunIcon,
} from "./icons";
import { Lockup } from "./Logo";

// The logo leads home: the default view, but the category shown.
const { category: _category, ...HOME } = DEFAULT_STATE;

const THEME_ICONS: Record<ThemePreference, () => JSX.Element> = {
  auto: AutoThemeIcon,
  light: SunIcon,
  dark: MoonIcon,
};

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
  /** The day of the store's last update, as shown. */
  lastUpdate: string | null;
  readingListSize: number;
  /** The archive's years (or last 12 months) the highly cited view shows, which the graph and Rankings take. */
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
  const ThemeIcon = THEME_ICONS[props.theme];
  return (
    <header class="topbar">
      <div class="topbar__brand">
        <h1>
          <a class="site-logo" {...props.tab(false, HOME)}>
            <Lockup />
          </a>
        </h1>
        {props.lastUpdate && <span class="muted topbar__updated">Updated {props.lastUpdate}</span>}
      </div>
      <div class="topbar__tools">
        <nav class="tabs" aria-label="Views">
          <a
            class={`tab${view === "papers" ? " tab--active" : ""}`}
            {...tab(view === "papers", { view: "papers", year: null })}
          >
            <PapersIcon />
            <span class="tab__label">Papers</span>
          </a>
          <a
            class={`tab${view === "graph" ? " tab--active" : ""}`}
            // From the highly cited papers, the graph shows them.
            {...tab(view === "graph", {
              view: "graph",
              ...(cited ? { year: props.archiveRange } : {}),
            })}
          >
            <GraphIcon />
            <span class="tab__label">Graph</span>
          </a>
          <a
            class={`tab${cited ? " tab--active" : ""}`}
            title="The most cited papers of each year of first version, and of the last 12 months"
            {...tab(cited, { view: "cited" })}
          >
            <CitedIcon />
            <span class="tab__label">Highly cited</span>
          </a>
          <a
            class={`tab${view === "rankings" ? " tab--active" : ""}`}
            title="Institutions, authors and countries of the papers shown, by papers or citations"
            {...tab(view === "rankings", {
              view: "rankings",
              ...(cited ? { year: props.archiveRange } : {}),
            })}
          >
            <RankingsIcon />
            <span class="tab__label">Rankings</span>
          </a>
          <a
            class={`tab${view === "reading-list" ? " tab--active" : ""}`}
            // Where a saved paper's star flies to (UX-37).
            data-tab="reading-list"
            {...tab(view === "reading-list", { view: "reading-list" })}
          >
            <StarIcon />
            <span class="tab__label">Reading list ({props.readingListSize.toLocaleString()})</span>
          </a>
          <a
            class={`tab${view === "about" ? " tab--active" : ""}`}
            title="Where the data comes from, corrections and privacy"
            {...tab(view === "about", { view: "about" })}
          >
            <InfoIcon />
            <span class="tab__label">About</span>
          </a>
        </nav>
        <button
          type="button"
          class="icon-button"
          title={`Theme: ${props.theme} — click for ${props.nextTheme}`}
          aria-label={`Theme: ${props.theme}. Switch to ${props.nextTheme}.`}
          onClick={props.onTheme}
        >
          <ThemeIcon />
        </button>
      </div>
    </header>
  );
}
