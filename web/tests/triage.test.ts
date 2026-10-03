import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadSeen, newSince, previousVisit, pruneSeen, saveSeen } from "../src/triage";

function stubStorage(name: "localStorage" | "sessionStorage"): Map<string, string> {
  const stored = new Map<string, string>();
  vi.stubGlobal(name, {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => stored.set(key, value),
  });
  return stored;
}

describe("seen papers", () => {
  beforeEach(() => stubStorage("localStorage"));
  afterEach(() => vi.unstubAllGlobals());

  it("keep the papers of the last three months", () => {
    const today = new Date(2026, 9, 3);
    expect(
      pruneSeen(["2610.00001", "2607.12345", "2606.00002", "cs/0601001", "junk"], today),
    ).toEqual(["2610.00001", "2607.12345"]);
    expect(pruneSeen(["2509.00001", "2510.00001"], new Date(2026, 0, 15))).toEqual(["2510.00001"]);
  });

  it("are remembered per category", () => {
    saveSeen("cs.CV", new Set(["2609.30234"]), new Date(2026, 9, 3));
    expect(loadSeen("cs.CV")).toEqual(new Set(["2609.30234"]));
    expect(loadSeen("cs.LG")).toEqual(new Set());
    localStorage.setItem("preprint-radar:seen:cs.CV", '{"not": "a list"}');
    expect(loadSeen("cs.CV")).toEqual(new Set());
  });

  it("survive a storage that fails", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    });
    expect(loadSeen("cs.CV")).toEqual(new Set());
    expect(() => saveSeen("cs.CV", new Set(["2609.30234"]))).not.toThrow();
    expect(previousVisit("cs.CV", "2026-10-02")).toBeNull();
  });
});

describe("since last visit", () => {
  let local: Map<string, string>;
  let session: Map<string, string>;
  beforeEach(() => {
    local = stubStorage("localStorage");
    session = stubStorage("sessionStorage");
  });
  afterEach(() => vi.unstubAllGlobals());

  it("is the newest day of the previous session, stable within this one", () => {
    expect(previousVisit("cs.CV", "2026-09-30")).toBeNull();
    // A new session (the browser was closed): the day of the first one.
    session.clear();
    expect(previousVisit("cs.CV", "2026-10-02")).toBe("2026-09-30");
    // A reload in the same session does not make it empty.
    expect(previousVisit("cs.CV", "2026-10-02")).toBe("2026-09-30");
    expect(local.get("preprint-radar:last-visit:cs.CV")).toBe("2026-10-02");
  });

  it("counts the papers of the days announced since", () => {
    const days = [
      { date: "2026-10-02", count: 215 },
      { date: "2026-10-01", count: 224 },
      { date: "2026-09-30", count: 180 },
    ];
    expect(newSince(days, "2026-09-30")).toEqual({
      from: "2026-10-01",
      to: "2026-10-02",
      papers: 439,
    });
    expect(newSince(days, "2026-10-02")).toBeNull();
    expect(newSince(days, null)).toBeNull();
  });
});
