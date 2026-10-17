import { describe, expect, it } from "vitest";
import { fileVersions, withVersions } from "../tooling/data-versions";

describe("the versions of the data files (PERF-8)", () => {
  it("are the start of each file's digest, for the files that exist", () => {
    const files: Record<string, string> = {
      "cs.CV/2026-09-25.json": '{"papers": []}',
      "cs.CV/countries.json": '{"institutions": {}}',
    };
    const encoder = new TextEncoder();
    // A stand-in for SHA-256: the bytes' count, then their first one, as 64 hex digits.
    const digest = (content: Uint8Array) =>
      `${content.length.toString(16)}${(content[0] ?? 0).toString(16)}`.padEnd(64, "f");

    const versions = fileVersions(
      ["cs.CV/2026-09-25.json", "cs.CV/2026-09-24.json", "cs.CV/countries.json"],
      (path) => (path in files ? encoder.encode(files[path]) : null),
      digest,
    );

    expect(versions).toEqual(
      new Map([
        ["cs.CV/2026-09-25.json", "e7bfffffff"],
        ["cs.CV/countries.json", "147bffffff"],
      ]),
    );
  });

  it("go into the site's index, by path, keeping the rest", () => {
    const index = JSON.stringify({ schema_version: 1, categories: { "cs.CV": [] } }, null, 1);
    const versions = new Map([
      ["cs.CV/2026-09-25.json", "bbbbbbbbbb"],
      ["cs.CV/2026-09-24.json", "aaaaaaaaaa"],
    ]);

    const written = JSON.parse(withVersions(index, versions));

    expect(written).toEqual({
      schema_version: 1,
      categories: { "cs.CV": [] },
      versions: { "cs.CV/2026-09-24.json": "aaaaaaaaaa", "cs.CV/2026-09-25.json": "bbbbbbbbbb" },
    });
    expect(Object.keys(written.versions)).toEqual([
      "cs.CV/2026-09-24.json",
      "cs.CV/2026-09-25.json",
    ]);
  });
});
