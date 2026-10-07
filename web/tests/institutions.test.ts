import { describe, expect, it } from "vitest";
import { acronymOf, institutionsOf, namedInstitutions } from "../src/institutions";
import { makePaper } from "./fixtures";

describe("institutionsOf", () => {
  it("gives the institutions the pipeline named, null where none", () => {
    const paper = makePaper({
      arxiv_id: "20",
      affiliations: ["University of Padova, Italy", "Department of Physics", "CMU"],
      institutions: ["University of Padua", null, "Carnegie Mellon University"],
    });

    expect(institutionsOf(paper)).toEqual([
      "University of Padua",
      null,
      "Carnegie Mellon University",
    ]);
  });

  it("names none for a record not named yet, or out of step with its affiliations", () => {
    const unnamed = makePaper({
      arxiv_id: "21",
      affiliations: ["MIT", "Inria"],
      institutions: null,
    });
    expect(institutionsOf(unnamed)).toEqual([null, null]);
    expect(
      institutionsOf(
        makePaper({ arxiv_id: "22", affiliations: ["MIT", "Inria"], institutions: ["X"] }),
      ),
    ).toEqual([null, null]);
  });
});

describe("namedInstitutions", () => {
  it("keeps the named institutions, in order, without the gaps", () => {
    const paper = makePaper({
      arxiv_id: "23",
      affiliations: ["Department of Physics", "CMU", "Inria"],
      institutions: [null, "Carnegie Mellon University", "Inria"],
    });

    expect(namedInstitutions(paper)).toEqual(["Carnegie Mellon University", "Inria"]);
    expect(namedInstitutions(makePaper({ arxiv_id: "24", affiliations: null }))).toEqual([]);
  });
});

describe("acronymOf", () => {
  it("gives the institution an acronym written alone stands for", () => {
    expect(acronymOf("NUS")).toBe("National University of Singapore");
    expect(acronymOf(" cuhk-sz ")).toBe("Chinese University of Hong Kong, Shenzhen");
  });

  it("names none for anything else", () => {
    expect(acronymOf("NUS Singapore")).toBeNull();
    expect(acronymOf("")).toBeNull();
  });
});
