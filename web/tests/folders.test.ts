import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  addFolder,
  deleteFolder,
  FOLDERS_KEY,
  type Folder,
  findFolder,
  folderName,
  folderOf,
  loadFolders,
  MAX_FOLDER_NAME,
  mergeFolders,
  putPaper,
  readFolders,
  renameFolder,
  saveFolders,
} from "../src/folders";

const folders: Folder[] = [
  { name: "To read", papers: ["2609.00001", "2609.00002"] },
  { name: "Splatting", papers: ["2609.00003"] },
];

describe("folder names", () => {
  it("are trimmed, collapsed and cut", () => {
    expect(folderName("  To   read \n")).toBe("To read");
    expect(folderName("x".repeat(100))).toHaveLength(MAX_FOLDER_NAME);
    expect(folderName("   ")).toBe("");
  });

  it("find a folder whatever the case", () => {
    expect(findFolder(folders, "to READ")?.name).toBe("To read");
    expect(findFolder(folders, "Diffusion")).toBeUndefined();
    expect(findFolder(folders, null)).toBeUndefined();
  });

  it("say which folder holds a paper", () => {
    expect(folderOf(folders, "2609.00003")).toBe("Splatting");
    expect(folderOf(folders, "2609.00009")).toBeNull();
  });
});

describe("readFolders", () => {
  it("reads what was stored", () => {
    expect(readFolders(folders)).toEqual(folders);
  });

  it("skips what an untrusted file holds that is not a folder", () => {
    expect(readFolders("folders")).toEqual([]);
    expect(
      readFolders([
        null,
        "To read",
        { name: "  ", papers: [] },
        { name: 3, papers: [] },
        { name: " To  read ", papers: ["2609.00001", "javascript:alert(1)", 4, "2609.00001"] },
        // Another folder of the same name, whatever its case, and one without papers.
        { name: "to read", papers: ["2609.00005"] },
        { name: "Later" },
        // A paper is in the first folder holding it only.
        { name: "Again", papers: ["2609.00001", "2609.00006"] },
      ]),
    ).toEqual([
      { name: "To read", papers: ["2609.00001"] },
      { name: "Later", papers: [] },
      { name: "Again", papers: ["2609.00006"] },
    ]);
  });
});

describe("changing folders", () => {
  it("adds a folder with a new name only", () => {
    expect(addFolder(folders, " Diffusion ").at(-1)).toEqual({ name: "Diffusion", papers: [] });
    expect(addFolder(folders, "to read")).toBe(folders);
    expect(addFolder(folders, "  ")).toBe(folders);
  });

  it("renames a folder in place, not onto another's name", () => {
    expect(renameFolder(folders, "Splatting", "Gaussian splatting")[1]).toEqual({
      name: "Gaussian splatting",
      papers: ["2609.00003"],
    });
    expect(renameFolder(folders, "to read", "TO READ")[0]?.name).toBe("TO READ");
    expect(renameFolder(folders, "Splatting", "to read")).toBe(folders);
    expect(renameFolder(folders, "Splatting", " ")).toBe(folders);
    expect(renameFolder(folders, "Diffusion", "Models")).toBe(folders);
  });

  it("deletes a folder, not its papers' records", () => {
    expect(deleteFolder(folders, "to read")).toEqual([folders[1]]);
    expect(deleteFolder(folders, "Diffusion")).toBe(folders);
  });

  it("puts a paper in one folder at most", () => {
    const moved = putPaper(folders, "2609.00003", "To read");
    expect(moved).toEqual([
      { name: "To read", papers: ["2609.00003", "2609.00001", "2609.00002"] },
      { name: "Splatting", papers: [] },
    ]);
    expect(putPaper(moved, "2609.00003", null)).toEqual([
      { name: "To read", papers: ["2609.00001", "2609.00002"] },
      { name: "Splatting", papers: [] },
    ]);
    expect(putPaper(folders, "2609.00003", "splatting")).toBe(folders);
    expect(putPaper(folders, "2609.00009", null)).toBe(folders);
  });

  it("merges an imported file's folders by name", () => {
    const {
      folders: merged,
      added,
      kept,
    } = mergeFolders(folders, [
      // The file's papers already in a folder here stay where they are, and are counted.
      { name: "to read", papers: ["2609.00007", "2609.00003", "2609.00001"] },
      { name: "Diffusion", papers: ["2609.00008", "2609.00009"] },
    ]);
    expect([added, kept]).toEqual([1, 1]);
    expect(merged).toEqual([
      { name: "To read", papers: ["2609.00007", "2609.00001", "2609.00002"] },
      { name: "Splatting", papers: ["2609.00003"] },
      { name: "Diffusion", papers: ["2609.00008", "2609.00009"] },
    ]);
    expect(mergeFolders(folders, [{ name: "Splatting", papers: ["2609.00003"] }])).toEqual({
      folders,
      added: 0,
      kept: 0,
    });
  });
});

describe("stored folders", () => {
  beforeEach(() => {
    const stored = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => stored.set(key, value),
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("load back what was saved", () => {
    expect(loadFolders()).toEqual([]);
    expect(saveFolders(folders)).toBe(true);
    expect(localStorage.getItem(FOLDERS_KEY)).toBe(JSON.stringify(folders));
    expect(loadFolders()).toEqual(folders);
  });

  it("fall back to none when the storage is refused or unreadable", () => {
    localStorage.setItem(FOLDERS_KEY, "{not json");
    expect(loadFolders()).toEqual([]);
    const refuse = () => {
      throw new Error("denied");
    };
    vi.stubGlobal("localStorage", { getItem: refuse, setItem: refuse });
    expect(loadFolders()).toEqual([]);
    expect(saveFolders(folders)).toBe(false);
  });
});
