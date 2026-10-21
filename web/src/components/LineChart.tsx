import { useEffect, useId, useRef, useState } from "preact/hooks";
import { areaPath, linePath, niceTicks, xScale } from "../chart";

/** A line of the chart. */
export interface ChartSeries {
  key: string;
  name: string;
  /** Its value at each point; `null` where it has none. */
  values: readonly (number | null)[];
  /** Its color, a tone of `styles.css` (`chart__line--rising`): never the text's. */
  tone: string;
}

/** Points the chart shades, with what they are: the periods a window compares. */
export interface ChartBand {
  from: number;
  to: number;
  label: string;
}

interface Props {
  /** What the chart shows: the table's caption, and the plot's name for screen readers. */
  title: string;
  /** What a point is, the table's first column: "Month". */
  pointName: string;
  /** Each point's name, in the tooltip and the table: "Oct 2026". */
  labels: readonly string[];
  /** The points the axis names, with their tick: [12, "2025"]. */
  ticks: readonly (readonly [number, string])[];
  series: readonly ChartSeries[];
  bands?: readonly ChartBand[];
  /** A value as the axis and the tooltip write it: "2.0%". */
  format: (value: number) => string;
  /** More about a point of a line, after its value: "74 papers". */
  detail?: (series: ChartSeries, index: number) => string;
  /** The area under a single line. */
  area?: boolean;
  height?: number;
}

const MARGIN = { top: 22, right: 14, bottom: 26, left: 46 };
/** The room the lines' names take at their end, when the chart is wide enough for them. */
const END_LABELS = 112;
const WIDE_ENOUGH = 520;
/** Names closer than this at the lines' end would collide: the legend says them instead. */
const LABEL_GAP = 14;

/**
 * A line chart drawn in SVG (PROD-20): thin lines over hairline gridlines, a crosshair that
 * snaps to the nearest point under the pointer or the arrow keys, with every line's value
 * at it, and a table of the same values, the chart's equivalent for screen readers and
 * print. Several lines have a legend, and their names at their ends where they fit apart.
 */
export function LineChart(props: Props) {
  const { labels, series, format } = props;
  const height = props.height ?? 220;
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const describedBy = useId();
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    setWidth(element.clientWidth);
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [table]);

  const several = series.length > 1;
  const values = series.flatMap((line) => line.values.filter((value) => value !== null));
  const ticks = niceTicks(Math.max(0, ...values));
  const top = ticks.at(-1) ?? 0;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;
  const y = (value: number) => MARGIN.top + plotHeight * (top > 0 ? 1 - value / top : 1);
  // The lines' names at their ends, where the chart is wide enough and they stand apart.
  const ends = series.map((line) => {
    const last = line.values.findLastIndex((value) => value !== null);
    return { line, last, at: last < 0 ? null : y(line.values[last] ?? 0) };
  });
  const sorted = ends.flatMap(({ at }) => (at === null ? [] : [at])).sort((a, b) => a - b);
  const apart = sorted.every(
    (at, index) => index === 0 || at - (sorted[index - 1] ?? 0) >= LABEL_GAP,
  );
  const labeled = several && width >= WIDE_ENOUGH && apart;
  const right = labeled ? END_LABELS : MARGIN.right;
  const plotWidth = Math.max(0, width - MARGIN.left - right);
  const x = xScale(labels.length, MARGIN.left, plotWidth);
  const step = labels.length > 1 ? plotWidth / (labels.length - 1) : plotWidth;
  const shown = active === null ? null : Math.min(active, labels.length - 1);

  const describe = (index: number) =>
    `${labels[index] ?? ""}: ${series
      .map((line) => {
        const value = line.values[index];
        const text = value === null || value === undefined ? "none" : format(value);
        const more = props.detail?.(line, index);
        return `${several ? `${line.name} ` : ""}${text}${more ? `, ${more}` : ""}`;
      })
      .join("; ")}`;

  const onKeyDown = (event: KeyboardEvent) => {
    const last = labels.length - 1;
    const from = shown ?? last;
    const to =
      event.key === "ArrowLeft"
        ? from - 1
        : event.key === "ArrowRight"
          ? from + 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (event.key === "Escape") {
      setActive(null);
      return;
    }
    if (to === null) return;
    event.preventDefault();
    setActive(Math.min(last, Math.max(0, to)));
  };

  return (
    <figure class="chart">
      <div class="chart__bar">
        {several && (
          <ul class="chart__legend">
            {series.map((line) => (
              <li class="chart__legend-item" key={line.key}>
                <svg class="chart__key" viewBox="0 0 16 4" aria-hidden="true">
                  <path class={`chart__line chart__line--${line.tone}`} d="M1 2h14" />
                </svg>
                {line.name}
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          class="link-button chart__toggle"
          aria-pressed={table}
          onClick={() => setTable(!table)}
        >
          {table ? "Show the chart" : "Show as a table"}
        </button>
      </div>
      {table ? (
        <div class="chart__table">
          <table>
            <caption class="visually-hidden">{props.title}</caption>
            <thead>
              <tr>
                <th class="chart__cell" scope="col">
                  {props.pointName}
                </th>
                {series.map((line) => (
                  <th class="chart__cell" scope="col" key={line.key}>
                    {line.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {labels.map((label, index) => (
                <tr key={label}>
                  <th class="chart__cell" scope="row">
                    {label}
                  </th>
                  {series.map((line) => {
                    const value = line.values[index];
                    const more = props.detail?.(line, index);
                    return (
                      <td class="chart__cell" key={line.key}>
                        {value === null || value === undefined ? "–" : format(value)}
                        {more && <span class="muted"> · {more}</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        // biome-ignore lint/a11y/useSemanticElements: the chart's points, which the arrow keys go through: no form's fieldset
        <div
          class="chart__plot"
          ref={box}
          // biome-ignore lint/a11y/noNoninteractiveTabindex: the arrow keys move the crosshair, as the pointer does
          tabIndex={0}
          role="group"
          aria-label={`${props.title}: the arrow keys go from point to point`}
          aria-describedby={describedBy}
          onKeyDown={onKeyDown}
          onFocus={() => setActive((current) => current ?? labels.length - 1)}
          onBlur={() => setActive(null)}
        >
          {width > 0 && (
            <svg
              class="chart__svg"
              width={width}
              height={height}
              aria-hidden="true"
              onPointerMove={(event) => {
                const bounds = event.currentTarget.getBoundingClientRect();
                setActive(x.nearest(event.clientX - bounds.left));
              }}
              onPointerLeave={() => setActive(null)}
            >
              {props.bands?.map((band) => {
                const from = Math.max(MARGIN.left, x.at(band.from) - step / 2);
                const to = Math.min(MARGIN.left + plotWidth, x.at(band.to) + step / 2);
                return to > from ? (
                  <g key={band.label}>
                    <rect
                      class="chart__band"
                      x={from}
                      y={MARGIN.top}
                      width={to - from}
                      height={plotHeight}
                    />
                    <text class="chart__band-label" x={from + 4} y={MARGIN.top - 8}>
                      {band.label}
                    </text>
                  </g>
                ) : null;
              })}
              {ticks.map((tick) => (
                <g key={tick}>
                  <line
                    class={tick === 0 ? "chart__axis" : "chart__grid"}
                    x1={MARGIN.left}
                    x2={MARGIN.left + plotWidth}
                    y1={y(tick)}
                    y2={y(tick)}
                  />
                  <text
                    class="chart__tick"
                    x={MARGIN.left - 6}
                    y={y(tick)}
                    dy="0.32em"
                    text-anchor="end"
                  >
                    {format(tick)}
                  </text>
                </g>
              ))}
              {props.ticks.map(([index, text]) => (
                <text
                  key={index}
                  class="chart__tick"
                  x={x.at(index)}
                  y={height - 8}
                  text-anchor="middle"
                >
                  {text}
                </text>
              ))}
              {props.area && series.length === 1 && series[0] && (
                <path
                  class={`chart__area chart__area--${series[0].tone}`}
                  d={areaPath(series[0].values, x.at, y, y(0))}
                />
              )}
              {series.map((line) => (
                <path
                  key={line.key}
                  class={`chart__line chart__line--${line.tone}`}
                  d={linePath(line.values, x.at, y)}
                />
              ))}
              {labeled &&
                ends.map(({ line, last, at }) =>
                  at === null ? null : (
                    <text key={line.key} class="chart__end" x={x.at(last) + 8} y={at} dy="0.32em">
                      {line.name}
                    </text>
                  ),
                )}
              {shown !== null && (
                <g>
                  <line
                    class="chart__crosshair"
                    x1={x.at(shown)}
                    x2={x.at(shown)}
                    y1={MARGIN.top}
                    y2={MARGIN.top + plotHeight}
                  />
                  {series.map((line) => {
                    const value = line.values[shown];
                    return value === null || value === undefined ? null : (
                      <circle
                        key={line.key}
                        class={`chart__dot chart__dot--${line.tone}`}
                        cx={x.at(shown)}
                        cy={y(value)}
                        r={4}
                      />
                    );
                  })}
                </g>
              )}
            </svg>
          )}
          {shown !== null && width > 0 && (
            <div
              class={`chart__tip${x.at(shown) > width / 2 ? " chart__tip--left" : ""}`}
              style={{ left: `${x.at(shown)}px`, top: `${MARGIN.top}px` }}
              aria-hidden="true"
            >
              <span class="chart__tip-label">{labels[shown]}</span>
              {series.map((line) => {
                const value = line.values[shown];
                const more = props.detail?.(line, shown);
                return (
                  <span class="chart__tip-row" key={line.key}>
                    <svg class="chart__key" viewBox="0 0 16 4" aria-hidden="true">
                      <path class={`chart__line chart__line--${line.tone}`} d="M1 2h14" />
                    </svg>
                    <strong>{value === null || value === undefined ? "–" : format(value)}</strong>
                    {several && <span>{line.name}</span>}
                    {more && <span class="muted">{more}</span>}
                  </span>
                );
              })}
            </div>
          )}
          <p class="visually-hidden" id={describedBy} aria-live="polite">
            {shown === null ? "" : describe(shown)}
          </p>
        </div>
      )}
    </figure>
  );
}
