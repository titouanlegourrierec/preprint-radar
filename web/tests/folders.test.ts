import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  addFolder,
  addPaper,
  deleteFolder,
  FOLDERS_KEY,
  type Folder,
  findFolder,
  folderName,
  foldersOf,
  forgetPaper,
  loadFolders,
  MAX_FOLDER_NAME,
  mergeFolders,
  readFolders,
  removePaper,
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

  it("say which folders hold a paper", () => {
    expect(foldersOf(folders, "2609.00003")).toEqual(["Splatting"]);
    expect(foldersOf(folders, "2609.00009")).toEqual([]);
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
        // A paper can be in several folders (UX-45).
        { name: "Again", papers: ["2609.00001", "2609.00006"] },
      ]),
    ).toEqual([
      { name: "To read", papers: ["2609.00001"] },
      { name: "Later", papers: [] },
      { name: "Again", papers: ["2609.00001", "2609.00006"] },
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

  it("puts a paper in several folders, first, and takes it out of one (UX-45)", () => {
    const both = addPaper(folders, "2609.00003", "to read");
    expect(both).toEqual([
      { name: "To read", papers: ["2609.00003", "2609.00001", "2609.00002"] },
      { name: "Splatting", papers: ["2609.00003"] },
    ]);
    expect(foldersOf(both, "2609.00003")).toEqual(["To read", "Splatting"]);
    expect(removePaper(both, "2609.00003", "Splatting")).toEqual([
      { name: "To read", papers: ["2609.00003", "2609.00001", "2609.00002"] },
      { name: "Splatting", papers: [] },
    ]);
    // Nothing to change: the same folders.
    expect(addPaper(folders, "2609.00003", "splatting")).toBe(folders);
    expect(addPaper(folders, "2609.00003", "Diffusion")).toBe(folders);
    expect(removePaper(folders, "2609.00009", "To read")).toBe(folders);
    expect(removePaper(folders, "2609.00001", "Diffusion")).toBe(folders);
  });

  it("takes an unsaved paper out of every folder", () => {
    expect(forgetPaper(addPaper(folders, "2609.00003", "To read"), "2609.00003")).toEqual([
      { name: "To read", papers: ["2609.00001", "2609.00002"] },
      { name: "Splatting", papers: [] },
    ]);
    expect(forgetPaper(folders, "2609.00009")).toBe(folders);
  });

  it("merges an imported file's folders by name", () => {
    const { folders: merged, added } = mergeFolders(folders, [
      // A paper in another folder here goes in the file's too, and stays in its own.
      { name: "to read", papers: ["2609.00007", "2609.00003", "2609.00001"] },
      { name: "Diffusion", papers: ["2609.00008", "2609.00009"] },
    ]);
    expect(added).toBe(1);
    expect(merged).toEqual([
      { name: "To read", papers: ["2609.00007", "2609.00003", "2609.00001", "2609.00002"] },
      { name: "Splatting", papers: ["2609.00003"] },
      { name: "Diffusion", papers: ["2609.00008", "2609.00009"] },
    ]);
    expect(mergeFolders(folders, [{ name: "Splatting", papers: ["2609.00003"] }])).toEqual({
      folders,
      added: 0,
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
