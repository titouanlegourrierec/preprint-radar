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
    // Its papers are not triaged, but their abstracts can be shown (PROD-14).
    expect(cited).toMatchObject({ triaged: false, hideSeen: false, abstracts: true });
    expect(
      viewModel(state({ view: "cited" }), { hasSearchWords: true, gainsKnown: true }).sorts,
    ).toEqual(["citations", "rising"]);
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
    expect(list.sorts).toEqual(["newest", "citations"]);
    // Its abstracts are always shown; its Export menu is the other lists' (SRCH-16).
    expect(list).toMatchObject({
      triaged: false,
      hideSeen: false,
      abstracts: false,
      exports: true,
    });
  });
});
