import type { Paper } from "./types";

const STORAGE_KEY = "preprint-radar:reading-list";

/** Papers saved by the user, persisted in the browser (full records, so they survive data pruning). */
export function loadReadingList(): Paper[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as Paper[]) : [];
  } catch {
    return [];
  }
}

export function saveReadingList(papers: Paper[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(papers));
  } catch {
    // Storage may be full or disabled (private browsing); the list then lives for the session.
  }
}
