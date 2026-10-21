import type { JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { LAST_12_MONTHS } from "../archive-years";
import { linePath, xScale } from "../chart";
import { loadTrends } from "../data";
import { countOf, formatDay } from "../format";
import { LOCALE } from "../locale";
import { NO_FILTERS } from "../search";
import {
  COMPARED,
  displayName,
  formatChange,
  formatPercent,
  formatShare,
  impactMonths,
  type ListName,
  monthAfter,
  monthLabel,
  periodMonths,
  shareOf,
  shares,
  type TrendRow,
  type TrendsFile,
  type TrendTopic,
  topicQuery,
  trendRows,
  type WindowName,
} from "../trends";
import { Explorer } from "./Explorer";
import { InfoButton } from "./InfoButton";
import { CloseIcon, CoolingIcon, NewIcon, RisingIcon } from "./icons";
import { type ChartBand, LineChart } from "./LineChart";
import { Segmented } from "./Segmented";
import type { TabLink } from "./Topbar";

interface Props {
  category: string | null;
  window: WindowName;
  /** The topic opened, by its key. */
  topic: string | null;
  /** The topics the explorer draws, by key. */
  compare: string[];
  onWindow: (window: WindowName) => void;
  onTopic: (topic: string | null) => void;
  onCompare: (keys: string[]) => void;
  /** A link to another state of the site: a topic opened, its papers in another view. */
  link: TabLink;
}

type Loaded =
  | { status: "loading" }
  | { status: "ready"; file: TrendsFile }
  | { status: "missing" }
  | { status: "error"; message: string };

const WINDOW_OPTIONS = [
  ["quarter", "90 days"],
  ["year", "12 months"],
] as const;
const WINDOW_TITLES = {
  quarter: "The last 90 days against the same days a year before",
  year: "The last 12 months against the 12 before",
};

const LISTS = [
  {
    list: "rising",
    title: "Rising",
    note: "Their share of the papers grew the most",
    Icon: RisingIcon,
  },
  {
    list: "cooling",
    title: "Cooling",
    note: "Their share of the papers fell the most",
    Icon: CoolingIcon,
  },
  { list: "new", title: "New", note: "First seen within the last 12 months", Icon: NewIcon },
] as const;
/** The rows of a list shown before "Show all". */
const FIRST_ROWS = 10;

/**
 * The tone of a topic: the color of its lines, by the list that names it (a new topic rises);
 * neutral for one opened that the window does not list.
 */
type Tone = "rising" | "cooling" | "neutral";

/**
 * The Trends view (PROD-20): the topics of the category's titles whose share of the papers
 * rose, fell or first appeared, over the last 90 days or 12 months against the same before
 * (`trends.json`, which the weekly archive writes), and a topic's months, impact and most
 * cited papers when opened.
 */
export function Trends(props: Props) {
  const { category } = props;
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (category === null) return;
    let live = true;
    setLoaded({ status: "loading" });
    loadTrends(category)
      .then((file) => {
        if (live) setLoaded(file ? { status: "ready", file } : { status: "missing" });
      })
      .catch((error: unknown) => {
        if (live) {
          setLoaded({
            status: "error",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      live = false;
    };
  }, [category, attempt]);

  // A topic a link opened stays where it is; one opened from the lists is brought into view.
  const linked = useRef(props.topic);
  useEffect(() => {
    if (props.topic !== linked.current) linked.current = null;
  }, [props.topic]);

  const file = loaded.status === "ready" ? loaded.file : null;
  const compared = file?.windows[props.window];
  const opened = props.topic === null ? undefined : file?.topics[props.topic];

  return (
    <main class="trends" id="main">
      <header class="trends__head">
        <div class="trends__title">
          <h2>Trends{category ? ` in ${category}` : ""}</h2>
          <p class="muted">
            The topics of the papers' titles whose share of the papers rose, fell, or first
            appeared:{" "}
            {props.window === "quarter"
              ? `the last 90 days${compared ? `, ${formatDay(compared.recent[0])} to ${formatDay(compared.recent[1])},` : ""} against the same days a year before.`
              : "the last 12 months against the 12 before."}
          </p>
        </div>
        <div class="trends__controls">
          <Segmented
            legend="Periods compared"
            options={WINDOW_OPTIONS}
            value={props.window}
            onChange={props.onWindow}
            titles={WINDOW_TITLES}
          />
          <InfoButton label="How the topics are counted" end>
            <Method source={file?.source} />
          </InfoButton>
        </div>
      </header>

      {loaded.status === "loading" ? (
        <p class="notice" role="status">
          Loading the trends…
        </p>
      ) : loaded.status === "missing" ? (
        <p class="notice">
          The topics of the titles are counted every week, with the archive of highly cited papers:
          they are not there yet.
        </p>
      ) : loaded.status === "error" ? (
        <p class="notice notice--error" role="alert">
          Could not load the trends: {loaded.message}.{" "}
          <button type="button" class="link-button" onClick={() => setAttempt(attempt + 1)}>
            Retry
          </button>
        </p>
      ) : (
        <>
          {props.topic !== null &&
            (opened && compared ? (
              <TopicPanel
                key={props.topic}
                file={loaded.file}
                windowName={props.window}
                topicKey={props.topic}
                topic={opened}
                link={props.link}
                focus={props.topic !== linked.current}
                compare={props.compare}
                onCompare={props.onCompare}
                onClose={() => props.onTopic(null)}
              />
            ) : (
              <p class="notice">
                “{props.topic}” is not among the topics listed this week.{" "}
                <button type="button" class="link-button" onClick={() => props.onTopic(null)}>
                  Close
                </button>
              </p>
            ))}
          <div class="trend-lists">
            {LISTS.map(({ list, title, note, Icon }) => (
              <TrendList
                key={list}
                list={list}
                title={title}
                note={note}
                icon={<Icon />}
                rows={trendRows(loaded.file, props.window, list)}
                file={loaded.file}
                windowName={props.window}
                opened={props.topic}
                link={props.link}
              />
            ))}
          </div>
          {category && (
            <Explorer
              category={category}
              compare={props.compare}
              onCompare={props.onCompare}
              suggestions={suggestionsOf(loaded.file, props.window)}
            />
          )}
          <p class="trends__source muted">
            Counted to {formatDay(loaded.file.through)}, from {loaded.file.source}, every week.
          </p>
        </>
      )}
    </main>
  );
}

/** Topics the explorer offers to try: the window's first two rising and cooling. */
function suggestionsOf(file: TrendsFile, window: WindowName): { key: string; name: string }[] {
  const compared = file.windows[window];
  const keys = [...(compared?.rising.slice(0, 2) ?? []), ...(compared?.cooling.slice(0, 2) ?? [])];
  return keys.flatMap((key) => {
    const topic = file.topics[key];
    return topic ? [{ key, name: topic.name }] : [];
  });
}

/** How the topics are counted, behind the view's ⓘ. */
function Method({ source }: { source: string | undefined }) {
  return (
    <>
      <p>
        A topic is a phrase of the titles, one to four words ("world model", "vision-language-action
        model"), or an acronym ("VLA"): a title says what a paper is about. Its share of the papers
        is compared between two periods of the same days a year apart, which the conferences'
        seasons do not bias.
      </p>
      <p>
        A topic rises when its share grows, and cools when it falls, ranked by how much: ×4.7 is a
        share 4.7 times what it was, −64% one that lost almost two thirds, the share of a few papers
        added to both periods so that one paper becoming six does not lead. Two phrases sharing half
        their papers are one topic, which the more specific names. A new topic had its first month
        with three papers within the last 12 months.
      </p>
      <p>
        A topic's impact is the share of its papers among the most cited tenth of their month: 10%
        for an average topic.{" "}
        {source?.includes("Semantic Scholar")
          ? "Titles from arXiv, citation counts from Semantic Scholar."
          : "Titles from arXiv."}
      </p>
    </>
  );
}

interface ListProps {
  list: ListName;
  title: string;
  note: string;
  icon: JSX.Element;
  rows: TrendRow[];
  file: TrendsFile;
  windowName: WindowName;
  opened: string | null;
  link: TabLink;
}

/** One of the view's lists: its topics, their months drawn, their papers then and now. */
function TrendList(props: ListProps) {
  const { list, rows, file } = props;
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, FIRST_ROWS);
  const months = file.windows[props.windowName]?.days === 365 ? 12 : 3;
  return (
    <section class={`trend-list trend-list--${list}`} aria-labelledby={`trend-list-${list}`}>
      <h3 class="trend-list__title" id={`trend-list-${list}`}>
        <span class={`trend-mark trend-mark--${list === "cooling" ? "cooling" : "rising"}`}>
          {props.icon}
        </span>
        {props.title}
      </h3>
      <p class="trend-list__note muted">{props.note}</p>
      {rows.length === 0 ? (
        <p class="trend-list__empty muted">None this time.</p>
      ) : (
        <ol class="trend-list__rows">
          {shown.map((row, index) => (
            <li key={row.key}>
              <a
                class={`trend-row${row.key === props.opened ? " trend-row--open" : ""}`}
                {...props.link(row.key === props.opened, { topic: row.key })}
              >
                <span class="trend-row__rank" aria-hidden="true">
                  {index + 1}
                </span>
                <span class="trend-row__name">{displayName(row.topic.name)}</span>
                {list === "new" ? (
                  <>
                    <span class="trend-row__change">{countOf(row.recent, "paper")}</span>
                    <Sparkline
                      values={shares(row.topic.counts, file.totals)}
                      recent={months}
                      tone="rising"
                    />
                    <span class="trend-row__counts muted">
                      {row.topic.first ? `from ${monthLabel(row.topic.first)}` : "new"}
                    </span>
                  </>
                ) : (
                  <>
                    <span class="trend-row__change">{formatChange(row.lift)}</span>
                    <Sparkline
                      values={shares(row.topic.counts, file.totals)}
                      recent={months}
                      tone={list}
                    />
                    <span class="trend-row__counts muted">
                      {row.earlier.toLocaleString(LOCALE)}
                      <span aria-hidden="true"> → </span>
                      <span class="visually-hidden"> to </span>
                      {countOf(row.recent, "paper")}
                    </span>
                  </>
                )}
              </a>
            </li>
          ))}
        </ol>
      )}
      {rows.length > FIRST_ROWS && (
        <button type="button" class="link-button trend-list__more" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${rows.length}`}
        </button>
      )}
    </section>
  );
}

/**
 * A topic's share of the papers over the last three years, in its row: a gray line, the
 * window's recent months in the tone of where its share went.
 */
function Sparkline({ values, recent, tone }: { values: number[]; recent: number; tone: Tone }) {
  const width = 88;
  const height = 22;
  const max = Math.max(0, ...values);
  const x = xScale(values.length, 1, width - 2);
  const y = (value: number) => (max > 0 ? height - 2 - (height - 4) * (value / max) : height - 2);
  const split = Math.max(0, values.length - recent - 1);
  return (
    <svg
      class="sparkline"
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      aria-hidden="true"
    >
      <path
        class="sparkline__past"
        d={linePath(
          values.map((value, index) => (index <= split ? value : null)),
          x.at,
          y,
        )}
      />
      <path
        class={`sparkline__recent sparkline__recent--${tone}`}
        d={linePath(
          values.map((value, index) => (index >= split ? value : null)),
          x.at,
          y,
        )}
      />
    </svg>
  );
}

interface PanelProps {
  file: TrendsFile;
  windowName: WindowName;
  topicKey: string;
  topic: TrendTopic;
  link: TabLink;
  /** Opened from the lists: brought into view and focused. */
  focus: boolean;
  compare: string[];
  onCompare: (keys: string[]) => void;
  onClose: () => void;
}

/** A topic opened: its share month by month, its papers then and now, its impact and most cited papers. */
function TopicPanel(props: PanelProps) {
  const { file, windowName, topicKey, topic } = props;
  const compared = file.windows[windowName];
  const panel = useRef<HTMLElement>(null);
  // Brought into view and focused when opened from the lists, which are below it.
  useEffect(() => {
    const element = panel.current;
    if (!(element && props.focus)) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    element.scrollIntoView({ block: "start", behavior: still ? "auto" : "smooth" });
    element.focus({ preventScroll: true });
  }, []);
  if (compared === undefined) return null;
  const [then, now] = topic.windows[windowName] ?? [0, 0];
  const [before, after] = compared.papers;
  const isNew = compared.new.includes(topicKey);
  const tone: Tone = compared.cooling.includes(topicKey)
    ? "cooling"
    : isNew || compared.rising.includes(topicKey)
      ? "rising"
      : "neutral";
  const months = file.totals.map((_, index) => monthAfter(file.start, index));
  const last = months.length - 1;
  const labels = months.map((month, index) =>
    index === last ? `${monthLabel(month)}, to ${formatDay(file.through)}` : monthLabel(month),
  );
  const ticks = months.flatMap((month, index) =>
    month.endsWith("-01") ? [[index, month.slice(0, 4)] as const] : [],
  );
  const [thenMonths, nowMonths] = periodMonths(file, compared);
  const bands: ChartBand[] =
    windowName === "quarter"
      ? [
          { from: thenMonths[0], to: thenMonths[1], label: "A year before" },
          { from: nowMonths[0], to: nowMonths[1], label: "Last 90 days" },
        ]
      : [{ from: nowMonths[0], to: nowMonths[1], label: "Last 12 months" }];
  const [impactFrom, impactTo] = impactMonths(file);
  const recent = windowName === "quarter" ? "the last 90 days" : "the last 12 months";
  const earlier = windowName === "quarter" ? "the same days a year before" : "the 12 months before";
  const query = topicQuery(topicKey);
  const name = displayName(topic.name);
  const status = compared.rising.includes(topicKey)
    ? "Rising"
    : compared.cooling.includes(topicKey)
      ? "Cooling"
      : isNew
        ? "New"
        : null;
  return (
    <section class="topic" ref={panel} tabIndex={-1} aria-labelledby="topic-name">
      <div class="topic__head">
        <h3 id="topic-name">{name}</h3>
        {status && <span class={`topic__status topic__status--${tone}`}>{status}</span>}
        <button
          type="button"
          class="icon-button topic__close"
          aria-label="Close the topic"
          title="Close"
          onClick={props.onClose}
        >
          <CloseIcon />
        </button>
      </div>
      <p class="topic__summary">
        {countOf(now, "paper")} in {recent}, {then.toLocaleString(LOCALE)} in {earlier}: its share
        of the papers went from {formatShare(shareOf(then, before))} to{" "}
        {formatShare(shareOf(now, after))}.
        {topic.first && ` It first had three papers in a month in ${monthLabel(topic.first)}.`}
      </p>
      <dl class="topic__stats">
        <div class="stat">
          <dt>Papers, {recent}</dt>
          <dd>
            <span class="stat__value">{now.toLocaleString(LOCALE)}</span>
            <span class="stat__delta">from {then.toLocaleString(LOCALE)}</span>
          </dd>
        </div>
        <div class="stat">
          <dt>Share of the papers</dt>
          <dd>
            <span class="stat__value">{formatShare(shareOf(now, after))}</span>
            <span class="stat__delta">from {formatShare(shareOf(then, before))}</span>
          </dd>
        </div>
        <div class="stat">
          <dt>Impact</dt>
          <dd>
            <span class="stat__value">
              {topic.impact === null ? "–" : formatPercent(topic.impact)}
            </span>
            <span class="stat__delta">
              {topic.impact === null
                ? file.source.includes("Semantic Scholar")
                  ? "too few papers to say"
                  : "no citation counts this week"
                : `of its papers of ${monthLabel(impactFrom)} to ${monthLabel(impactTo)} among the most cited tenth of their month, 10% for any topic`}
            </span>
          </dd>
        </div>
      </dl>
      <h4 class="topic__chart-title">Its share of the papers, over the 3 months to each</h4>
      <LineChart
        title={`${name}: its share of the papers, over the 3 months to each`}
        pointName="Month"
        labels={labels}
        ticks={ticks}
        series={[{ key: topicKey, name, values: shares(topic.counts, file.totals), tone }]}
        bands={bands}
        format={formatShare}
        detail={(_, index) => countOf(topic.counts[index] ?? 0, "paper")}
        area
      />
      {topic.papers.length > 0 && (
        <section class="topic__papers" aria-labelledby="topic-papers">
          <h4 id="topic-papers">Its most cited papers of the last 12 months</h4>
          <ol>
            {topic.papers.map((paper) => (
              <li key={paper.id}>
                <a href={`https://arxiv.org/abs/${paper.id}`}>{paper.title}</a>{" "}
                <span class="muted">{countOf(paper.citations, "citation")}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
      <div class="topic__actions">
        <a
          class="button"
          {...props.link(false, {
            view: "papers",
            query,
            filters: NO_FILTERS,
            period: { kind: "since", from: compared.recent[0] },
            topic: null,
          })}
        >
          Its papers since {formatDay(compared.recent[0])}
        </a>
        <a
          class="button"
          {...props.link(false, {
            view: "cited",
            query,
            filters: NO_FILTERS,
            year: LAST_12_MONTHS,
            topic: null,
          })}
        >
          Its most cited of the last 12 months
        </a>
        <button
          type="button"
          class="button"
          disabled={props.compare.includes(topicKey) || props.compare.length >= COMPARED}
          onClick={() => {
            props.onCompare([...props.compare, topicKey]);
            const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
            document
              .getElementById("explorer")
              ?.scrollIntoView({ block: "start", behavior: still ? "auto" : "smooth" });
          }}
        >
          {props.compare.includes(topicKey) ? "In the explorer" : "Compare in the explorer"}
        </button>
      </div>
    </section>
  );
}
