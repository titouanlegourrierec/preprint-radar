/**
 * The topics of a category's titles, month by month (PROD-20): which rise, which cool, which
 * are new, as the weekly archive counts them (`trends.json`, `docs/trends.md`), and every
 * topic since 2010 for the explorer (`topics.json`). The pipeline ranks the topics; this
 * module only reads what it wrote, for the Trends view.
 */
import { LOCALE } from "./locale";
import { searchKey } from "./text";

/** One of a topic's most cited papers of the last 12 months. */
export interface KeyPaper {
  id: string;
  title: string;
  citations: number;
}

/** A topic the lists name. */
export interface TrendTopic {
  /** The phrase as titles most often write it: "vision-language-action model", "VLA". */
  name: string;
  /** Its papers in each month of the file. */
  counts: number[];
  /** Its papers in each window's two periods, the earlier first. */
  windows: Record<string, [number, number]>;
  /** The first month three of its papers appeared in ("2026-03"). */
  first: string | null;
  /**
   * Of its papers of 3 to 15 months before the last, the share among the most cited tenth
   * of their month; `null` with too few of them, or without citation counts.
   */
  impact: number | null;
  /** Its most cited papers of the last 12 months, the most cited first. */
  papers: KeyPaper[];
}

/** Two periods of the same days a year apart, and the topics their papers rank. */
export interface TrendWindow {
  days: number;
  /** The first and last day of the earlier period, and of the recent one. */
  earlier: [string, string];
  recent: [string, string];
  /** The papers of each period, the earlier first. */
  papers: [number, number];
  rising: string[];
  cooling: string[];
  new: string[];
  /** The share added to both of a topic's shares in its lift, which ranks the lists. */
  added: number;
}

/** `<category>/trends.json`, which the weekly archive writes. */
export interface TrendsFile {
  schema_version: number;
  category: string;
  generated_at: string;
  /** "arXiv", or "arXiv, Semantic Scholar" with the impact and key papers. */
  source: string;
  /** The last day counted. */
  through: string;
  /** The first month of `totals` and of each topic's counts ("2023-10"). */
  start: string;
  /** The category's papers in each month. */
  totals: number[];
  windows: Record<string, TrendWindow>;
  topics: Record<string, TrendTopic>;
}

/** A topic of `topics.json`: its papers a month, from its first. */
export interface TopicSeries {
  name: string;
  /** The index of its first month with a paper among the file's months. */
  start: number;
  counts: number[];
}

/** `<category>/topics.json`: every topic with enough papers since 2010, for the explorer. */
export interface TopicsFile {
  schema_version: number;
  category: string;
  generated_at: string;
  source: string;
  through: string;
  start: string;
  totals: number[];
  topics: Record<string, TopicSeries>;
}

/** The windows the lists compare: the last 90 days, and the last 12 months, with a year before. */
export type WindowName = "quarter" | "year";
export const WINDOW_NAMES: readonly WindowName[] = ["quarter", "year"];

export type ListName = "rising" | "cooling" | "new";

/** The months a share is counted over: a small topic's month holds a few papers. */
export const SMOOTHING = 3;

/** The month `months` after a month: `monthAfter("2023-10", 3)` is "2024-01". */
export function monthAfter(month: string, months: number): string {
  const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + months;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** The months from one to the other: `monthsBetween("2023-10", "2024-01")` is 3. */
export function monthsBetween(from: string, to: string): number {
  const index = (month: string) => Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7));
  return index(to) - index(from);
}

/** A month as the site writes it: "Oct 2026". */
export function monthLabel(month: string): string {
  return new Date(`${month}-01T00:00:00`).toLocaleDateString(LOCALE, {
    month: "short",
    year: "numeric",
  });
}

/**
 * A topic's share of the category's papers at each month, over the `span` months to it
 * (fewer at the start): a month of a small topic holds too few papers to say alone.
 */
export function shares(
  counts: readonly number[],
  totals: readonly number[],
  span = SMOOTHING,
): number[] {
  return counts.map((_, index) => {
    let papers = 0;
    let all = 0;
    for (let month = Math.max(0, index - span + 1); month <= index; month++) {
      papers += counts[month] ?? 0;
      all += totals[month] ?? 0;
    }
    return all > 0 ? papers / all : 0;
  });
}

/** A share of a period's papers, none of none. */
export function shareOf(papers: number, of: number): number {
  return of > 0 ? papers / of : 0;
}

/**
 * A topic's lift between a window's two periods, which orders the lists: the ratio of its
 * shares of the papers, the window's `added` share added to each, so that one paper becoming
 * six does not lead (`docs/trends.md`).
 */
export function lift(
  [then, now]: readonly [number, number],
  [before, after]: readonly [number, number],
  added: number,
): number {
  return (shareOf(now, after) + added) / (shareOf(then, before) + added);
}

/** A change as the lists write it: "×5.6" from twice the share, else "+40%", "−53%". */
export function formatChange(change: number): string {
  if (change >= 2) {
    const digits = change >= 10 ? 0 : 1;
    return `×${change.toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
  }
  const percent = Math.round((change - 1) * 100);
  return percent < 0 ? `−${-percent}%` : `+${percent}%`;
}

/** A share of the papers, to two significant digits: "2.0%", "0.36%", "12%". */
export function formatShare(share: number): string {
  if (share === 0) return "0%";
  const percent = (share * 100).toLocaleString(LOCALE, {
    minimumSignificantDigits: 2,
    maximumSignificantDigits: 2,
  });
  return `${percent}%`;
}

/** A topic's name as a list or a heading writes it, from a capital: "World model", "VLA", "3D gaussian splatting". */
export function displayName(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** A share as a whole percentage: "54%". */
export function formatPercent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

/** A phrase's plural, as a title writes it: "world models", "robot policies", "patches". */
function plural(phrase: string): string {
  if (/[^aeiou]y$/.test(phrase)) return `${phrase.slice(0, -1)}ies`;
  if (/(?:s|x|z|ch|sh)$/.test(phrase)) return `${phrase}es`;
  return `${phrase}s`;
}

/**
 * The site's search for a topic: its phrase, singular or plural, as titles write either
 * (`"world model" OR "world models"`). A quoted phrase matches whole words of the folded
 * text, hyphens as spaces ("semi supervised" finds "Semi-Supervised").
 */
export function topicQuery(key: string): string {
  return `"${key}" OR "${plural(key)}"`;
}

/** A topic of a window's list, and how its share changed. */
export interface TrendRow {
  key: string;
  topic: TrendTopic;
  /** Its papers in the earlier period, and in the recent one. */
  earlier: number;
  recent: number;
  /** Its lift, which orders the rising and cooling lists. */
  lift: number;
}

/** A window's list, as the view shows it; a topic the file lacks is left out. */
export function trendRows(file: TrendsFile, window: WindowName, list: ListName): TrendRow[] {
  const shown = file.windows[window];
  if (shown === undefined) return [];
  return shown[list].flatMap((key) => {
    const topic = file.topics[key];
    const pair = topic?.windows[window];
    if (topic === undefined || pair === undefined) return [];
    return [
      {
        key,
        topic,
        earlier: pair[0],
        recent: pair[1],
        lift: lift(pair, shown.papers, shown.added),
      },
    ];
  });
}

/** The months the window's periods fall in, as indices of the file's months: where the chart shades them. */
export function periodMonths(
  file: TrendsFile,
  window: TrendWindow,
): [[number, number], [number, number]] {
  const at = (day: string) => monthsBetween(file.start, day.slice(0, 7));
  return [
    [at(window.earlier[0]), at(window.earlier[1])],
    [at(window.recent[0]), at(window.recent[1])],
  ];
}

/**
 * The months a topic's impact counts its papers of: 3 to 15 months before the file's last,
 * old enough to be cited, recent enough to be the topic as it is.
 */
export function impactMonths(file: TrendsFile): [string, string] {
  const last = file.totals.length - 1;
  return [monthAfter(file.start, last - 15), monthAfter(file.start, last - 3)];
}

/** A topic the explorer offers for the words typed. */
export interface FoundTopic {
  key: string;
  name: string;
  /** Its papers since 2010. */
  papers: number;
}

/**
 * The topics whose words start with those typed, in any order ("wor mod" finds "world
 * model"): the one typed whole first, then the shorter, then those of more papers.
 */
export function findTopics(file: TopicsFile, text: string, limit = 8): FoundTopic[] {
  const typed = searchKey(text);
  const words = typed.split(" ").filter(Boolean);
  if (words.length === 0) return [];
  const found: FoundTopic[] = [];
  for (const [key, series] of Object.entries(file.topics)) {
    const own = key.split(" ");
    if (words.every((word) => own.some((part) => part.startsWith(word)))) {
      found.push({ key, name: series.name, papers: series.counts.reduce((a, b) => a + b, 0) });
    }
  }
  const rank = (topic: FoundTopic) => (topic.key === typed ? 0 : 1);
  return found
    .sort(
      (a, b) =>
        rank(a) - rank(b) ||
        a.key.split(" ").length - b.key.split(" ").length ||
        b.papers - a.papers ||
        a.key.localeCompare(b.key),
    )
    .slice(0, limit);
}
