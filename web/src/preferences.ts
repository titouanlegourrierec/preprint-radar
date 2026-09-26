const SHOW_ABSTRACTS_KEY = "preprint-radar:show-abstracts";
const GRAPH_SETTINGS_KEY = "preprint-radar:graph-settings";

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
  institutions: boolean;
  authors: boolean;
  /** Show nodes that share no paper with another shown node. */
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
  labelThreshold: number;
}

export const DEFAULT_GRAPH_SETTINGS: Readonly<GraphSettings> = {
  institutions: true,
  authors: false,
  isolated: true,
  minInstitutionPapers: 1,
  minAuthorPapers: 1,
  maxNodes: 0,
  centerForce: 0.3,
  repelForce: 12,
  linkForce: 1,
  linkDistance: 40,
  nodeSize: 1,
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
  return settings;
}

export function saveGraphSettings(settings: GraphSettings): void {
  try {
    localStorage.setItem(GRAPH_SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // Storage may be disabled (private browsing); settings then last for the session.
  }
}
