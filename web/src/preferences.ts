import type { NodeSizing } from "./graph-renderer";

const SHOW_ABSTRACTS_KEY = "preprint-radar:show-abstracts";
// v2: papers joined the graph, and the defaults changed with them.
const GRAPH_SETTINGS_KEY = "preprint-radar:graph-settings:v2";
// Also read by the inline script in index.html, which restores the theme before first paint.
const THEME_KEY = "preprint-radar:theme";

/** "auto" follows the system scheme; "light" and "dark" force one. */
export type ThemePreference = "auto" | "light" | "dark";

/** The theme chosen with the toggle, remembered in this browser. */
export function loadTheme(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : "auto";
  } catch {
    return "auto";
  }
}

export function saveTheme(theme: ThemePreference): void {
  try {
    if (theme === "auto") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage may be disabled (private browsing); the choice then lasts for the session.
  }
}

/** Whether abstracts are shown in the list, remembered in this browser. */
export function loadShowAbstracts(): boolean {
  try {
    return localStorage.getItem(SHOW_ABSTRACTS_KEY) === "true";
  } catch {
    return false;
  }
}

export function saveShowAbstracts(show: boolean): void {
  try {
    localStorage.setItem(SHOW_ABSTRACTS_KEY, String(show));
  } catch {
    // Storage may be disabled (private browsing); the choice then lasts for the session.
  }
}

/** Settings of the graph view, remembered in this browser. */
export interface GraphSettings {
  papers: boolean;
  institutions: boolean;
  authors: boolean;
  /** Show nodes without any link to another shown node. */
  isolated: boolean;
  minInstitutionPapers: number;
  minAuthorPapers: number;
  /** Maximum number of nodes; 0 shows them all. */
  maxNodes: number;
  centerForce: number;
  repelForce: number;
  linkForce: number;
  linkDistance: number;
  nodeSize: number;
  /** What node areas show: papers (institutions and authors) or citations (every node). */
  sizeBy: NodeSizing;
  labelThreshold: number;
}

const NODE_SIZINGS: readonly NodeSizing[] = ["papers", "citations"];

export const DEFAULT_GRAPH_SETTINGS: Readonly<GraphSettings> = {
  papers: true,
  institutions: true,
  authors: false,
  // A quarter of the papers have no affiliations: shown, they would be lone squares.
  isolated: false,
  minInstitutionPapers: 1,
  minAuthorPapers: 1,
  maxNodes: 0,
  centerForce: 0.3,
  repelForce: 12,
  linkForce: 1,
  linkDistance: 40,
  nodeSize: 1,
  sizeBy: "papers",
  labelThreshold: 1,
};

/** Stored settings merged over the defaults; unknown or mistyped values are ignored. */
export function loadGraphSettings(): GraphSettings {
  const settings: GraphSettings = { ...DEFAULT_GRAPH_SETTINGS };
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(GRAPH_SETTINGS_KEY) ?? "{}");
    if (typeof stored !== "object" || stored === null) return settings;
    for (const [key, value] of Object.entries(stored)) {
      if (Object.hasOwn(settings, key)) {
        const name = key as keyof GraphSettings;
        if (typeof value === typeof settings[name]) Object.assign(settings, { [name]: value });
      }
    }
  } catch {
    // Unreadable storage or invalid JSON: fall back to the defaults.
  }
  // A string, but maybe not one of the choices (an older or edited value).
  if (!NODE_SIZINGS.includes(settings.sizeBy)) settings.sizeBy = DEFAULT_GRAPH_SETTINGS.sizeBy;
  return settings;
}

export function saveGraphSettings(settings: GraphSettings): void {
  try {
    localStorage.setItem(GRAPH_SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // Storage may be disabled (private browsing); settings then last for the session.
  }
}
