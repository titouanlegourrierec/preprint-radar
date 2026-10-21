import { describe, expect, it } from "vitest";
import singularCases from "../../tests/fixtures/singular-cases.json?raw";
import {
  assignSlots,
  displayName,
  findTopics,
  formatChange,
  formatPercent,
  formatShare,
  impactMonths,
  lift,
  monthAfter,
  monthLabel,
  monthsBetween,
  periodMonths,
  quarterly,
  shareOf,
  shares,
  singular,
  type TopicsFile,
  type TrendsFile,
  topicNote,
  topicOfQuery,
  topicQuery,
  trendRows,
} from "../src/trends";

/** Thirteen months, October 2025 to October 2026, and the window of 90 days. */
const TRENDS: TrendsFile = {
  schema_version: 1,
  category: "cs.CV",
  generated_at: "2026-10-25T06:00:00+00:00",
  source: "arXiv, Semantic Scholar",
  through: "2026-10-20",
  start: "2025-10",
  totals: [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 200],
  windows: {
    quarter: {
      days: 90,
      earlier: ["2025-07-23", "2025-10-20"],
      recent: ["2026-07-23", "2026-10-20"],
      papers: [1_000, 2_000],
      rising: ["world model", "vla", "gone"],
      cooling: ["diffusion model"],
      new: ["vla"],
      added: 0.005,
    },
  },
  topics: {
    "world model": {
      name: "world model",
      counts: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 4, 20],
      windows: { quarter: [10, 100] },
      first: "2023-03",
      impact: 0.54,
      papers: [{ id: "2512.13030", title: "Motus", citations: 335 }],
    },
    vla: {
      name: "VLA",
      counts: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 9],
      windows: { quarter: [1, 47] },
      first: "2026-09",
      impact: null,
      papers: [],
    },
    "diffusion model": {
      name: "diffusion model",
      counts: [9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9],
      windows: { quarter: [266, 125] },
      first: "2021-11",
      impact: 0.09,
      papers: [],
    },
  },
};

describe("months", () => {
  it("count from a month, across years", () => {
    expect(monthAfter("2023-10", 3)).toBe("2024-01");
    expect(monthAfter("2010-01", 201)).toBe("2026-10");
    expect(monthAfter("2024-01", -1)).toBe("2023-12");
    expect(monthsBetween("2023-10", "2024-01")).toBe(3);
    expect(monthLabel("2026-10")).toBe("Oct 2026");
  });
});

describe("shares", () => {
  it("are a topic's papers over the category's, over the months to each", () => {
    expect(shares([1, 2, 3, 0], [10, 10, 10, 10], 2)).toEqual([0.1, 0.15, 0.25, 0.15]);
    // A month without papers says nothing.
    expect(shares([0, 1], [0, 10])).toEqual([0, 0.1]);
  });
});

describe("lift", () => {
  it("is the ratio of a topic's two shares, a share added to each", () => {
    expect(lift([10, 100], [1_000, 2_000], 0)).toBe(5);
    expect(lift([10, 100], [1_000, 2_000], 0.005)).toBeCloseTo(0.055 / 0.015, 9);
    // A topic new then: its share added to none.
    expect(lift([0, 100], [1_000, 2_000], 0.01)).toBeCloseTo(6, 9);
    expect(lift([10, 100], [0, 2_000], 0.05)).toBeCloseTo(2, 9);
    expect(shareOf(3, 0)).toBe(0);
  });

  it("is written as times from twice, else as a percentage", () => {
    expect(formatChange(5.6)).toBe("×5.6");
    expect(formatChange(3)).toBe("×3.0");
    expect(formatChange(12.4)).toBe("×12");
    expect(formatChange(1.4)).toBe("+40%");
    expect(formatChange(1)).toBe("+0%");
    expect(formatChange(0.47)).toBe("−53%");
  });

  it("gives a share two significant digits", () => {
    expect(formatShare(0.0203)).toBe("2.0%");
    expect(formatShare(0.0036)).toBe("0.36%");
    expect(formatShare(0.124)).toBe("12%");
    expect(formatShare(0)).toBe("0%");
  });
});

describe("names", () => {
  it("start with a capital, acronyms as written", () => {
    expect(displayName("world model")).toBe("World model");
    expect(displayName("VLA")).toBe("VLA");
    expect(displayName("3D gaussian splatting")).toBe("3D gaussian splatting");
    expect(formatPercent(0.542)).toBe("54%");
  });
});

describe("a search's topic", () => {
  it("is keyed as the pipeline keys it, its last word singular", () => {
    const cases = JSON.parse(singularCases) as { word: string; singular: string }[];
    expect(cases.length).toBeGreaterThan(10);
    for (const { word, singular: expected } of cases) expect(singular(word)).toBe(expected);
    expect(topicOfQuery("World Models")).toBe("world model");
    expect(topicOfQuery('"world model" OR "world models"')).toBe("world model");
    expect(topicOfQuery("Semi-Supervised")).toBe("semi supervised");
    expect(topicOfQuery("  ")).toBeNull();
  });

  it("says where the lists put it, the 90 days first", () => {
    expect(topicNote(TRENDS, "world model")).toEqual({
      key: "world model",
      name: "world model",
      list: "rising",
      window: "quarter",
      figure: "×3.7",
    });
    expect(topicNote(TRENDS, "diffusion model")?.figure).toBe("−75%");
    expect(topicNote(TRENDS, "gone")).toBeNull();
    // In no list of a window the file has.
    const unlisted = { ...TRENDS, windows: {} };
    expect(topicNote(unlisted, "world model")).toBeNull();
  });
});

describe("topicQuery", () => {
  it("searches the phrase and its plural", () => {
    expect(topicQuery("world model")).toBe('"world model" OR "world models"');
    expect(topicQuery("robot policy")).toBe('"robot policy" OR "robot policies"');
    expect(topicQuery("visual token patch")).toBe('"visual token patch" OR "visual token patches"');
    expect(topicQuery("vla")).toBe('"vla" OR "vlas"');
  });
});

describe("trendRows", () => {
  it("lists a window's topics with their change, leaving out those the file lacks", () => {
    const rising = trendRows(TRENDS, "quarter", "rising");
    expect(rising.map(({ key, earlier, recent }) => [key, earlier, recent])).toEqual([
      ["world model", 10, 100],
      ["vla", 1, 47],
    ]);
    expect(rising[0]?.lift).toBeCloseTo(0.055 / 0.015, 9);
    expect(trendRows(TRENDS, "quarter", "cooling")[0]?.lift).toBeCloseTo(0.0675 / 0.271, 9);
    expect(trendRows(TRENDS, "year", "rising")).toEqual([]);
  });

  it("finds the months of the periods and of the impact", () => {
    const quarter = TRENDS.windows.quarter;
    expect(quarter && periodMonths(TRENDS, quarter)).toEqual([
      [-3, 0],
      [9, 12],
    ]);
    expect(impactMonths(TRENDS)).toEqual(["2025-07", "2026-07"]);
  });
});

describe("findTopics", () => {
  const TOPICS: TopicsFile = {
    schema_version: 1,
    category: "cs.CV",
    generated_at: "2026-10-25T06:00:00+00:00",
    source: "arXiv",
    through: "2026-10-20",
    start: "2010-01",
    totals: [10, 10, 10],
    topics: {
      world: { name: "world", start: 0, counts: [5, 5, 5] },
      "world model": { name: "world model", start: 1, counts: [2, 3] },
      "video world model": { name: "video world model", start: 2, counts: [1] },
      "open world": { name: "open world", start: 0, counts: [9, 9, 9] },
      mamba: { name: "mamba", start: 2, counts: [4] },
    },
  };

  it("finds topics by the start of their words, the one typed first", () => {
    expect(findTopics(TOPICS, "World Model").map(({ key }) => key)).toEqual([
      "world model",
      "video world model",
    ]);
    expect(findTopics(TOPICS, "wor").map(({ key }) => key)).toEqual([
      "world",
      "open world",
      "world model",
      "video world model",
    ]);
    expect(findTopics(TOPICS, "wor", 1)).toEqual([{ key: "world", name: "world", papers: 15 }]);
    expect(findTopics(TOPICS, " ")).toEqual([]);
    expect(findTopics(TOPICS, "transformer")).toEqual([]);
  });
});

describe("the explorer", () => {
  it("keeps each topic's color, the new ones taking the first free", () => {
    const first = assignSlots(new Map(), ["mamba", "transformer", "nerf"]);
    expect([...first]).toEqual([
      ["mamba", 0],
      ["transformer", 1],
      ["nerf", 2],
    ]);
    // Mamba removed: the others keep theirs; GAN takes the slot left.
    expect([...assignSlots(first, ["transformer", "nerf", "gan"])]).toEqual([
      ["transformer", 1],
      ["nerf", 2],
      ["gan", 0],
    ]);
    // A slot asked twice goes to the first.
    expect([
      ...assignSlots(
        new Map([
          ["a", 0],
          ["b", 0],
        ]),
        ["a", "b"],
      ),
    ]).toEqual([
      ["a", 0],
      ["b", 1],
    ]);
  });

  it("counts the topics by quarter, from the one their first paper fell in", () => {
    const file: TopicsFile = {
      schema_version: 1,
      category: "cs.CV",
      generated_at: "2026-10-25T06:00:00+00:00",
      source: "arXiv",
      through: "2026-10-20",
      start: "2025-11",
      // November 2025 to October 2026.
      totals: [10, 10, 10, 20, 20, 20, 30, 30, 30, 40, 40, 5],
      topics: {
        mamba: { name: "mamba", start: 1, counts: [1, 1, 2, 2, 2, 0, 0, 0, 0, 0, 1] },
        vla: { name: "VLA", start: 6, counts: [3, 3, 3, 4, 4, 1] },
      },
    };
    const drawn = quarterly(file, ["vla", "mamba", "gone"]);
    // From the quarter of December 2025, Mamba's first month, to October 2026's.
    expect(drawn.labels).toEqual(["2025 Q4", "2026 Q1", "2026 Q2", "2026 Q3", "2026 Q4"]);
    expect(drawn.starts).toEqual([-1, 2, 5, 8, 11]);
    expect(drawn.papers).toEqual([
      [0, 0, 6, 11, 1],
      [1, 5, 2, 0, 1],
    ]);
    expect(drawn.shares[0]).toEqual([0, 0, 6 / 80, 11 / 110, 1 / 5]);
    expect(quarterly(file, []).labels).toEqual(["2026 Q4"]);
  });
});
