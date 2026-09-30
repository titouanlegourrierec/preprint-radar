import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_GRAPH_SETTINGS, loadGraphSettings, saveGraphSettings } from "../src/preferences";

describe("graph settings", () => {
  beforeEach(() => {
    const stored = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => stored.set(key, value),
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("defaults to sizing nodes by papers", () => {
    expect(loadGraphSettings().sizeBy).toBe("papers");
  });

  it("remembers sizing by citations", () => {
    saveGraphSettings({ ...DEFAULT_GRAPH_SETTINGS, sizeBy: "citations" });
    expect(loadGraphSettings().sizeBy).toBe("citations");
  });

  it("ignores a sizing it does not know", () => {
    localStorage.setItem("preprint-radar:graph-settings:v2", JSON.stringify({ sizeBy: "degree" }));
    expect(loadGraphSettings().sizeBy).toBe("papers");
  });
});
