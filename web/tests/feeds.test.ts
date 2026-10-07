import { describe, expect, it } from "vitest";
import { feedOf, feedSlug, institutionFeedPath, venueFeedPath } from "../src/feeds";
import { exactly, NO_FILTERS, typed } from "../src/search";
import { feedFiles } from "../tooling/feeds";
import { makePaper } from "./fixtures";

describe("feed paths", () => {
  it("name a feed by the search key of its name", () => {
    expect(feedSlug("Massachusetts Institute of Technology")).toBe(
      "massachusetts-institute-of-technology",
    );
    expect(feedSlug("Université Paris-Saclay")).toBe("universite-paris-saclay");
    expect(feedSlug("Justus-Liebig-Universität Gießen")).toBe("justus-liebig-universitat-giessen");
    expect(institutionFeedPath("cs.CV", "Google (DeepMind)")).toBe(
      "feeds/cs.CV/institutions/google-deepmind.xml",
    );
    expect(institutionFeedPath("cs.CV", "?!")).toBeNull();
    expect(venueFeedPath("cs.CV", "NeurIPS")).toBe("feeds/cs.CV/venues/neurips.xml");
  });

  const known = () => true;

  it("are the feed of the institution clicked, else of the major venue", () => {
    const at = { ...NO_FILTERS, affiliation: exactly("MIT"), venue: "CVPR*" };
    expect(feedOf("cs.CV", at, known)).toEqual({
      path: "feeds/cs.CV/institutions/mit.xml",
      name: "MIT",
      kind: "institution",
    });
    // Typed text is no institution's name.
    expect(feedOf("cs.CV", { ...at, affiliation: typed("MIT") }, known)).toEqual({
      path: "feeds/cs.CV/venues/cvpr.xml",
      name: "CVPR",
      kind: "venue",
    });
    expect(feedOf("cs.CV", { ...NO_FILTERS, venue: "CVPR 2026" }, known)?.name).toBe("CVPR");
    expect(feedOf("cs.CV", { ...NO_FILTERS, venue: "CVPR 2026 Workshop" }, known)).toBeNull();
    expect(feedOf("cs.CV", { ...NO_FILTERS, venue: "TPAMI 2026" }, known)).toBeNull();
    expect(feedOf("cs.CV", { ...NO_FILTERS, venue: "*" }, known)).toBeNull();
    expect(feedOf("cs.CV", { ...NO_FILTERS, affiliation: exactly("?!") }, known)).toBeNull();
    expect(feedOf("cs.CV", NO_FILTERS, known)).toBeNull();
    // An institution of the archive alone has no feed: the venue's, if any, instead.
    expect(feedOf("cs.CV", at, () => false)?.path).toBe("feeds/cs.CV/venues/cvpr.xml");
    expect(
      feedOf("cs.CV", { ...NO_FILTERS, affiliation: exactly("OpenAI") }, () => false),
    ).toBeNull();
  });
});

describe("feedFiles", () => {
  const day = (date: string, count: number) => ({ date, count });
  const store = (extra: Record<string, unknown> = {}) => {
    const files: Record<string, unknown> = {
      "index.json": {
        schema_version: 1,
        generated_at: "2026-10-07T07:00:00+00:00",
        categories: { "cs.CV": [day("2026-10-07", 2), day("2026-07-01", 1)] },
      },
      "cs.CV/2026-10-07.json": {
        papers: [
          makePaper({
            arxiv_id: "2610.00002",
            announced: "2026-10-07",
            title: "Splats & <Gaussians>\u0007",
            authors: Array.from({ length: 12 }, (_, index) => `Author ${index}`),
            affiliations: ["MIT, Cambridge", "CSAIL"],
            institutions: ["MIT", "MIT"],
            abstract: 'A "quoted" abstract.',
            venue: "CVPR 2026",
          }),
          makePaper({
            arxiv_id: "2610.00001",
            announced: "2026-10-07",
            affiliations: ["mit"],
            institutions: ["mit"],
          }),
        ],
      },
      "cs.CV/2026-07-01.json": {
        papers: [
          makePaper({
            arxiv_id: "2607.00001",
            announced: "2026-07-01",
            affiliations: ["Old Lab", "MIT"],
            institutions: ["Old Lab", "MIT"],
          }),
        ],
      },
      ...extra,
    };
    return (path: string) => files[path] ?? null;
  };

  it("gives each institution of the days its recent papers, newest first", () => {
    const files = feedFiles(store(), null);
    const mit = files.get("feeds/cs.CV/institutions/mit.xml") ?? "";
    // Titled with its most frequent spelling; the paper naming it twice is there once.
    expect(mit).toContain("<title>MIT: cs.CV preprints</title>");
    expect(mit.match(/<entry>/g)).toHaveLength(2);
    expect(mit.indexOf("2610.00002")).toBeLessThan(mit.indexOf("2610.00001"));
    expect(mit).toContain("<updated>2026-10-07T00:00:00Z</updated>");
    expect(mit).toContain("<id>urn:preprint-radar:feeds/cs.CV/institutions/mit.xml</id>");
    expect(mit).not.toContain('rel="self"');
    // An institution of older days keeps its feed, without entries.
    const old = files.get("feeds/cs.CV/institutions/old-lab.xml") ?? "";
    expect(old).not.toContain("<entry>");
    expect(old).toContain("<updated>2026-10-07T00:00:00Z</updated>");
  });

  it("writes valid entries: escaped, without control characters, ten authors", () => {
    const mit = feedFiles(store(), null).get("feeds/cs.CV/institutions/mit.xml") ?? "";
    expect(mit).toContain("<title>Splats &amp; &lt;Gaussians&gt;</title>");
    expect(mit).toContain('<summary type="text">A &quot;quoted&quot; abstract.</summary>');
    expect(mit).toContain("<author><name>Author 9</name></author>");
    expect(mit).not.toContain("Author 10");
    expect(mit).toContain("<author><name>and 2 more</name></author>");
    expect(mit).toContain('<category term="CVPR 2026"/>');
    expect(mit).toContain(
      '<link rel="alternate" type="text/html" href="https://arxiv.org/abs/2610.00002"/>',
    );
  });

  it("gives each major venue its papers, with the venues Semantic Scholar names", () => {
    const scholar = {
      "cs.CV/scholar.json": {
        papers: { "2610.00001": { doi: null, venue: "CVPR 2025", author_ids: null } },
      },
    };
    const files = feedFiles(store(scholar), null);
    const cvpr = files.get("feeds/cs.CV/venues/cvpr.xml") ?? "";
    expect(cvpr.match(/<entry>/g)).toHaveLength(2);
    expect(files.get("feeds/cs.CV/venues/eccv.xml")).not.toContain("<entry>");
    expect([...files.keys()].filter((path) => path.includes("/venues/"))).toHaveLength(7);
  });

  it("links the feed and the site's view when the site's address is known", () => {
    const mit =
      feedFiles(store(), "https://example.org/radar").get("feeds/cs.CV/institutions/mit.xml") ?? "";
    expect(mit).toContain("<id>https://example.org/radar/feeds/cs.CV/institutions/mit.xml</id>");
    expect(mit).toContain(
      '<link rel="self" type="application/atom+xml" href="https://example.org/radar/feeds/cs.CV/institutions/mit.xml"/>',
    );
    expect(mit).toContain(
      '<link rel="alternate" type="text/html" href="https://example.org/radar/?cat=cs.CV&amp;at=MIT"/>',
    );
  });

  it("gives nothing without an index or days", () => {
    expect(feedFiles(() => null, null).size).toBe(0);
    const empty = { schema_version: 1, generated_at: "x", categories: { "cs.CV": [] } };
    expect(feedFiles((path) => (path === "index.json" ? empty : null), null).size).toBe(0);
  });
});
