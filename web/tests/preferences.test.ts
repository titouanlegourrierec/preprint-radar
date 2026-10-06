import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTHOR_LAYER_MIN_PAPERS,
  authorLayer,
  DEFAULT_GRAPH_SETTINGS,
  loadGraphIntroRead,
  loadGraphSettings,
  loadHideSeen,
  loadShowAbstracts,
  loadTheme,
  saveGraphIntroRead,
  saveGraphSettings,
  saveHideSeen,
  saveShowAbstracts,
  saveTheme,
} from "../src/preferences";

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

describe("display preferences", () => {
  beforeEach(() => {
    const stored = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => stored.set(key, value),
      removeItem: (key: string) => stored.delete(key),
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("are remembered", () => {
    expect([loadTheme(), loadShowAbstracts(), loadHideSeen(), loadGraphIntroRead()]).toEqual([
      "auto",
      false,
      false,
      false,
    ]);
    saveTheme("dark");
    saveShowAbstracts(true);
    saveHideSeen(true);
    saveGraphIntroRead();
    expect([loadTheme(), loadShowAbstracts(), loadHideSeen(), loadGraphIntroRead()]).toEqual([
      "dark",
      true,
      true,
      true,
    ]);
    saveTheme("auto");
    expect(loadTheme()).toBe("auto");
  });

  it("fall back on defaults when storage is refused", () => {
    const refuse = () => {
      throw new Error("denied");
    };
    vi.stubGlobal("localStorage", { getItem: refuse, setItem: refuse, removeItem: refuse });
    expect([loadTheme(), loadShowAbstracts(), loadHideSeen(), loadGraphIntroRead()]).toEqual([
      "auto",
      false,
      false,
      false,
    ]);
    expect(() => {
      saveTheme("light");
      saveShowAbstracts(true);
      saveHideSeen(true);
      saveGraphIntroRead();
      saveGraphSettings(DEFAULT_GRAPH_SETTINGS);
    }).not.toThrow();
    expect(loadGraphSettings()).toEqual(DEFAULT_GRAPH_SETTINGS);
  });
});

describe("authorLayer", () => {
  it("hides authors of a single paper when the layer turns on", () => {
    const settings = { ...DEFAULT_GRAPH_SETTINGS, minAuthorPapers: 1 };
    expect(authorLayer(settings, true)).toEqual({
      authors: true,
      minAuthorPapers: AUTHOR_LAYER_MIN_PAPERS,
    });
  });

  it("keeps a higher threshold, and changes nothing else when the layer turns off", () => {
    const settings = { ...DEFAULT_GRAPH_SETTINGS, minAuthorPapers: 5 };
    expect(authorLayer(settings, true)).toEqual({ authors: true });
    expect(authorLayer({ ...settings, minAuthorPapers: 1 }, false)).toEqual({ authors: false });
  });
});
