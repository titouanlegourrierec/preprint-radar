import { describe, expect, it } from "vitest";
import { oneYear } from "../src/archive-years";
import { DEFAULT_STATE, type ViewState } from "../src/url-state";
import { viewModel } from "../src/view-model";

const state = (patch: Partial<ViewState>) => ({ ...DEFAULT_STATE, ...patch });
const words = { hasSearchWords: true, gainsKnown: false };
const none = { hasSearchWords: false, gainsKnown: false };

describe("viewModel", () => {
  it("offers relevance with search words, newest and most cited on the Papers view", () => {
    const model = viewModel(state({}), words);
    expect(model.sorts).toEqual(["relevance", "newest", "citations"]);
    expect(model.sorted).toBe("relevance");
    expect(model.relevanceHelp).toBe(true);
    expect(model.groupByDay).toBe(false);
    expect(model).toMatchObject({
      triaged: true,
      hideSeen: true,
      abstracts: true,
      exports: true,
      archived: false,
    });
  });

  it("is in announcement order, by day, without search words", () => {
    const model = viewModel(state({}), none);
    expect(model.sorts).toEqual(["newest", "citations"]);
    expect(model).toMatchObject({ sorted: "newest", newest: true, groupByDay: true });
    expect(viewModel(state({ sort: "newest" }), words)).toMatchObject({
      sorted: "newest",
      groupByDay: true,
    });
  });

  it("ranks by citations, or by gains once they are known", () => {
    expect(viewModel(state({ sort: "citations" }), words)).toMatchObject({
      sorted: "citations",
      byCount: true,
      groupByDay: false,
    });
    // Rising without gains is Most cited.
    expect(viewModel(state({ sort: "rising" }), none)).toMatchObject({
      sorted: "citations",
      rising: false,
      byCount: true,
    });
    const rising = viewModel(state({ sort: "rising" }), {
      hasSearchWords: false,
      gainsKnown: true,
    });
    expect(rising).toMatchObject({ sorted: "rising", rising: true });
    expect(rising.sorts).toEqual(["newest", "citations", "rising"]);
  });

  it("ranks the highly cited view by citations, with a control only for Rising", () => {
    const cited = viewModel(state({ view: "cited" }), words);
    expect(cited).toMatchObject({ cited: true, archived: true, byCount: true, exports: true });
    expect(cited.sorts).toEqual([]);
    // Its cards say their rank (UX-36); the other lists' do not.
    expect(cited.ranked).toBe(true);
    expect(viewModel(state({ sort: "citations" }), words).ranked).toBe(false);
    // Its papers are not triaged, but their abstracts can be shown (PROD-14).
    expect(cited).toMatchObject({ triaged: false, hideSeen: false, abstracts: true });
    expect(
      viewModel(state({ view: "cited" }), { hasSearchWords: true, gainsKnown: true }).sorts,
    ).toEqual(["citations", "rising"]);
  });

  it("ranks by the stars of the code once they are known (PROD-18)", () => {
    const stars = { hasSearchWords: false, gainsKnown: false, starsKnown: true };
    const starred = viewModel(state({ sort: "stars" }), stars);
    expect(starred.sorts).toEqual(["newest", "citations", "stars"]);
    expect(starred).toMatchObject({
      sorted: "stars",
      starred: true,
      byCount: false,
      groupByDay: false,
    });
    // Without stars, the URL's sort falls back to the view's own order.
    expect(viewModel(state({ sort: "stars" }), none)).toMatchObject({
      sorted: "newest",
      starred: false,
    });
    // The highly cited view offers it too, ranked by stars instead of citations.
    const cited = viewModel(state({ view: "cited", sort: "stars" }), stars);
    expect(cited.sorts).toEqual(["citations", "stars"]);
    expect(cited).toMatchObject({ sorted: "stars", byCount: false });
    expect(viewModel(state({ view: "cited" }), stars)).toMatchObject({ sorted: "citations" });
    // Not in Rankings.
    expect(viewModel(state({ view: "rankings", sort: "stars" }), stars).starred).toBe(false);
  });

  it("ranks by the stars gained in the week once they are known (PROD-18)", () => {
    const gains = {
      hasSearchWords: true,
      gainsKnown: true,
      starsKnown: true,
      starGainsKnown: true,
    };
    const rising = viewModel(state({ sort: "rising-stars" }), gains);
    expect(rising.sorts).toEqual([
      "relevance",
      "newest",
      "citations",
      "rising",
      "stars",
      "rising-stars",
    ]);
    expect(rising).toMatchObject({
      sorted: "rising-stars",
      risingStars: true,
      starred: false,
      byCount: false,
      groupByDay: false,
    });
    // The reading list offers its own order too: seven in all.
    expect(viewModel(state({ view: "reading-list" }), gains).sorts).toHaveLength(7);
    // Before the gains, the URL's Rising stars is Most starred, as Rising is Most cited.
    const stars = { hasSearchWords: false, gainsKnown: false, starsKnown: true };
    const starred = viewModel(state({ sort: "rising-stars" }), stars);
    expect(starred.sorts).toEqual(["newest", "citations", "stars"]);
    expect(starred).toMatchObject({ sorted: "stars", starred: true, risingStars: false });
    // Without stars at all, the view's own order.
    expect(viewModel(state({ sort: "rising-stars" }), none)).toMatchObject({
      sorted: "newest",
      starred: false,
      risingStars: false,
      groupByDay: true,
    });
    // The highly cited view offers it, ranked by gains instead of citations.
    const cited = viewModel(state({ view: "cited", sort: "rising-stars" }), gains);
    expect(cited.sorts).toEqual(["citations", "rising", "stars", "rising-stars"]);
    expect(cited).toMatchObject({ sorted: "rising-stars", byCount: false });
    // Not in Rankings.
    expect(viewModel(state({ view: "rankings", sort: "rising-stars" }), gains).risingStars).toBe(
      false,
    );
  });

  it("offers no list controls in Rankings, the graph or About", () => {
    for (const view of ["rankings", "graph", "about"] as const) {
      expect(viewModel(state({ view }), words)).toMatchObject({
        sorts: [],
        relevanceHelp: false,
        hideSeen: false,
        abstracts: false,
        exports: false,
        triaged: false,
      });
    }
  });

  it("shows archive years in the graph and Rankings only when the URL has some", () => {
    expect(viewModel(state({ view: "rankings" }), none)).toMatchObject({
      rankings: true,
      archived: false,
    });
    expect(viewModel(state({ view: "rankings", year: oneYear(2017) }), none).archived).toBe(true);
    expect(viewModel(state({ view: "graph", year: oneYear(2017) }), none).archived).toBe(true);
    expect(viewModel(state({ view: "rankings" }), none).sorts).toEqual([]);
  });

  it("sorts and exports the reading list, without triage or toggles", () => {
    const list = viewModel(state({ view: "reading-list" }), none);
    expect(list.sorts).toEqual(["custom", "newest", "citations"]);
    // Its own order first, by default (UX-39), without day headings; relevance with words.
    expect(list).toMatchObject({ sorted: "custom", custom: true, groupByDay: false });
    const words = { hasSearchWords: true, gainsKnown: false };
    expect(viewModel(state({ view: "reading-list" }), words).sorted).toBe("relevance");
    expect(viewModel(state({ view: "reading-list", sort: "custom" }), words).sorted).toBe("custom");
    expect(viewModel(state({ view: "reading-list", sort: "newest" }), none).sorted).toBe("newest");
    // Elsewhere, a link's custom order is the view's own.
    expect(viewModel(state({ sort: "custom" }), none)).toMatchObject({
      sorted: "newest",
      custom: false,
    });
    // Its abstracts are always shown; its Export menu is the other lists' (SRCH-16).
    expect(list).toMatchObject({
      triaged: false,
      hideSeen: false,
      abstracts: false,
      exports: true,
    });
  });
});
