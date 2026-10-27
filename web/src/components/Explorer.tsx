import { useEffect, useRef, useState } from "preact/hooks";
import { loadTopics } from "../data";
import { countOf, formatDay } from "../format";
import {
  assignSlots,
  COMPARED,
  displayName,
  type FoundTopic,
  findTopics,
  formatShare,
  quarterly,
  type TopicsFile,
  topicEntry,
} from "../trends";
import { CloseIcon, SearchIcon } from "./icons";
import { type ChartSeries, LineChart } from "./LineChart";

interface Props {
  category: string;
  /** The topics drawn, by key, in the URL's order. */
  compare: string[];
  onCompare: (keys: string[]) => void;
  /** Topics to try when none is drawn: the lists' first. */
  suggestions: readonly { key: string; name: string }[];
}

type Loaded =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; file: TopicsFile }
  | { status: "missing" }
  | { status: "error"; message: string };

/** A year named on the axis every this many, past eight years drawn. */
const YEARS_APART = 2;

/**
 * The explorer of the Trends view (PROD-20): any topic of the titles since 2010, words
 * alone too ("mamba", "transformer"), its share of the papers by quarter, up to five on one
 * chart (`?compare=`). `topics.json` (400 kB) loads only when the field is first focused or
 * a link names topics.
 */
export function Explorer(props: Props) {
  const { category, compare, onCompare } = props;
  const [asked, setAsked] = useState(compare.length > 0);
  const [loaded, setLoaded] = useState<Loaded>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);
  const [text, setText] = useState("");
  // Each topic's color, kept while others come and go.
  const slots = useRef(new Map<string, number>());
  const wanted = asked || compare.length > 0;
  useEffect(() => {
    if (!wanted) return;
    let live = true;
    setLoaded({ status: "loading" });
    loadTopics(category)
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
  }, [wanted, category, attempt]);

  const file = loaded.status === "ready" ? loaded.file : null;
  const known = file ? compare.filter((key) => topicEntry(file.topics, key) !== null) : [];
  const unknown = file ? compare.filter((key) => topicEntry(file.topics, key) === null) : [];
  slots.current = assignSlots(slots.current, compare);
  const add = (key: string) => {
    if (!compare.includes(key) && compare.length < COMPARED) onCompare([...compare, key]);
    setText("");
  };
  const remove = (key: string) => onCompare(compare.filter((other) => other !== key));
  const nameOf = (key: string) =>
    displayName((file && topicEntry(file.topics, key)?.[1].name) ?? key);

  return (
    <section class="explorer" id="explorer" aria-labelledby="explorer-title">
      <h3 id="explorer-title">Explore a topic</h3>
      <p class="muted explorer__lede">
        Any topic of the titles since 2010, words alone too ("mamba", "transformer"): its share of
        the papers by quarter. Up to {COMPARED} side by side.
      </p>
      <div class="explorer__bar">
        <TopicFind
          value={text}
          onChange={setText}
          onFocus={() => setAsked(true)}
          matches={file ? findTopics(file, text).filter(({ key }) => !compare.includes(key)) : []}
          loading={loaded.status === "loading" || loaded.status === "idle"}
          full={compare.length >= COMPARED}
          onChoose={add}
        />
        {compare.length > 0 && (
          <ul class="explorer__chosen" aria-label="Topics drawn">
            {compare.map((key) => (
              <li key={key} class="explorer__topic">
                <svg class="chart__key" viewBox="0 0 16 4" aria-hidden="true">
                  <path
                    class={`chart__line chart__line--series-${(slots.current.get(key) ?? 0) + 1}`}
                    d="M1 2h14"
                  />
                </svg>
                {nameOf(key)}
                <button
                  type="button"
                  class="explorer__remove"
                  aria-label={`Remove ${nameOf(key)}`}
                  title="Remove"
                  onClick={() => remove(key)}
                >
                  <CloseIcon />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {compare.length === 0 && props.suggestions.length > 0 && (
        <p class="explorer__try">
          <span class="muted">Try</span>
          {props.suggestions.map(({ key, name }) => (
            <button type="button" class="chip" key={key} onClick={() => add(key)}>
              {displayName(name)}
            </button>
          ))}
        </p>
      )}
      {loaded.status === "missing" && wanted ? (
        <p class="notice">
          Every topic's months are counted every week, with the trends: they are not there yet.
        </p>
      ) : loaded.status === "error" ? (
        <p class="notice notice--error" role="alert">
          Could not load the topics: {loaded.message}.{" "}
          <button type="button" class="link-button" onClick={() => setAttempt(attempt + 1)}>
            Retry
          </button>
        </p>
      ) : loaded.status === "loading" && compare.length > 0 ? (
        <p class="notice" role="status">
          Loading the topics…
        </p>
      ) : null}
      {unknown.length > 0 && (
        <p class="notice">
          {unknown.map((key) => `“${key}”`).join(", ")}{" "}
          {unknown.length === 1 ? "is not a topic" : "are not topics"} of the titles.{" "}
          <button
            type="button"
            class="link-button"
            onClick={() => onCompare(compare.filter((key) => !unknown.includes(key)))}
          >
            Remove
          </button>
        </p>
      )}
      {file && known.length > 0 && <Comparison file={file} keys={known} slots={slots.current} />}
    </section>
  );
}

/** The topics drawn, by quarter, on one chart, with their papers in the tooltip and the table. */
function Comparison({
  file,
  keys,
  slots,
}: {
  file: TopicsFile;
  keys: string[];
  slots: ReadonlyMap<string, number>;
}) {
  const drawn = quarterly(file, keys);
  const last = drawn.labels.length - 1;
  const labels = drawn.labels.map((label, index) =>
    index === last ? `${label}, to ${formatDay(file.through)}` : label,
  );
  const years = new Set(drawn.labels.map((label) => label.slice(0, 4))).size;
  const ticks = drawn.labels.flatMap((label, index) =>
    label.endsWith("Q1") && (years <= 8 || Number(label.slice(0, 4)) % YEARS_APART === 0)
      ? [[index, label.slice(0, 4)] as const]
      : [],
  );
  const series: ChartSeries[] = keys.map((key, index) => ({
    key,
    name: displayName(topicEntry(file.topics, key)?.[1].name ?? key),
    values: drawn.shares[index] ?? [],
    tone: `series-${(slots.get(key) ?? 0) + 1}`,
  }));
  return (
    <LineChart
      title="The topics' share of the papers, by quarter"
      pointName="Quarter"
      labels={labels}
      ticks={ticks}
      series={series}
      format={formatShare}
      detail={(line, index) => countOf(drawn.papers[keys.indexOf(line.key)]?.[index] ?? 0, "paper")}
      // The topics drawn above it, each with its line's key, are its legend.
      legend={false}
      height={260}
    />
  );
}

interface FindProps {
  value: string;
  onChange: (text: string) => void;
  onFocus: () => void;
  matches: FoundTopic[];
  loading: boolean;
  /** Five topics drawn already: none can be added. */
  full: boolean;
  onChoose: (key: string) => void;
}

/**
 * The field that finds a topic, as the graph's Find field finds a node: a combobox whose
 * matches are listed under it, the arrow keys going through them, Enter adding one.
 */
function TopicFind(props: FindProps) {
  const [active, setActive] = useState<number | null>(null);
  const [listing, setListing] = useState(false);
  const typed = props.value.trim() !== "";
  const listed = listing && typed && props.matches.length > 0;
  return (
    <div class="topic-find">
      <span class="topic-find__icon">
        <SearchIcon />
      </span>
      <input
        type="search"
        /* biome-ignore lint/a11y/noRedundantRoles: as the graph's Find field, a search field
           without a list, whose matches are its listbox. */
        role="combobox"
        list={undefined}
        placeholder={props.full ? `${COMPARED} topics drawn` : "Find a topic…"}
        aria-label="Find a topic to draw"
        aria-autocomplete="list"
        aria-expanded={listed}
        aria-controls="topic-matches"
        aria-activedescendant={listed && active !== null ? `topic-match-${active}` : undefined}
        disabled={props.full}
        value={props.value}
        onInput={(event) => {
          setActive(null);
          props.onChange(event.currentTarget.value);
        }}
        onFocus={() => {
          setListing(true);
          props.onFocus();
        }}
        onBlur={() => {
          setListing(false);
          setActive(null);
        }}
        onKeyDown={(event) => {
          const last = props.matches.length - 1;
          if (event.key === "ArrowDown" && listed) {
            event.preventDefault();
            setActive(active === null || active >= last ? 0 : active + 1);
          } else if (event.key === "ArrowUp" && listed) {
            event.preventDefault();
            setActive(active === null || active <= 0 ? last : active - 1);
          } else if (event.key === "Enter" && listed) {
            event.preventDefault();
            const chosen = props.matches[active ?? 0];
            if (chosen) props.onChoose(chosen.key);
            setActive(null);
          }
        }}
      />
      {listing && typed && (
        <div class="topic-find__drop">
          {listed ? (
            <div id="topic-matches" class="topic-find__matches" role="listbox" aria-label="Topics">
              {props.matches.map((topic, index) => (
                <div
                  key={topic.key}
                  id={`topic-match-${index}`}
                  role="option"
                  tabIndex={-1}
                  aria-selected={index === active}
                  class={index === active ? "is-active" : undefined}
                  // Chosen before the field loses the focus, which would close the list.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    props.onChoose(topic.key);
                    setActive(null);
                  }}
                >
                  <span>{displayName(topic.name)}</span>
                  <span class="muted">{countOf(topic.papers, "paper")}</span>
                </div>
              ))}
            </div>
          ) : (
            <p class="topic-find__none muted" role="status">
              {props.loading ? "Loading the topics…" : "No topic of the titles has these words."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
