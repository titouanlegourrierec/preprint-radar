import { describe, expect, it } from "vitest";
import { candidateMonths, candidateYears, MAX_SHARED, readShare, shareHash } from "../src/share";

describe("a folder's link (UX-46)", () => {
  it("names the folder and its papers in the fragment, commas as they are", () => {
    const hash = shareHash("To read & more", ["2610.01234", "2609.12345"]);
    expect(hash).toBe("#folder=To%20read%20%26%20more&papers=2610.01234,2609.12345");
    expect(readShare(hash)).toEqual({ name: "To read & more", ids: ["2610.01234", "2609.12345"] });
  });

  it("reads an untrusted fragment: ids once, without their version, others left out", () => {
    expect(
      readShare(
        "#folder=%20%20To%20%20read%20&papers=2610.01234v2,javascript:alert(1),2610.01234,,1706.03762",
      ),
    ).toEqual({ name: "To read", ids: ["2610.01234", "1706.03762"] });
    // A link without a name, or with an encoded comma.
    expect(readShare("#papers=2610.01234%2C2609.12345")).toEqual({
      name: "Shared papers",
      ids: ["2610.01234", "2609.12345"],
    });
    expect(readShare("#folder=To%20read&papers=nothing")).toBeNull();
    expect(readShare("#results")).toBeNull();
    expect(readShare("")).toBeNull();
  });

  it("holds at most a thousand papers", () => {
    const ids = Array.from(
      { length: MAX_SHARED + 5 },
      (_, n) => `2610.${String(n).padStart(5, "0")}`,
    );
    expect(readShare(shareHash("Many", ids))?.ids).toHaveLength(MAX_SHARED);
    expect(readShare(`#papers=${ids.join(",")}`)?.ids).toHaveLength(MAX_SHARED);
  });
});

describe("where a shared paper is looked for", () => {
  it("is announced the month of its id or the next", () => {
    expect(candidateMonths("2609.12345")).toEqual(["2026-09", "2026-10"]);
    expect(candidateMonths("2512.01234")).toEqual(["2025-12", "2026-01"]);
    expect(candidateMonths("cs/0601001")).toEqual([]);
  });

  it("is archived under the year of its id, or the next for December's", () => {
    expect(candidateYears("1706.03762")).toEqual([2017]);
    expect(candidateYears("1712.00001")).toEqual([2017, 2018]);
    expect(candidateYears("cs/0601001")).toEqual([]);
  });
});
