/**
 * The geometry of the Trends view's line charts (PROD-20): the values of the axis, the
 * paths of the lines and the area, and the point under the pointer. `LineChart` draws them.
 */

/** A coordinate rounded to a tenth of a pixel, so that paths stay short. */
function rounded(value: number): number {
  return Math.round(value * 10) / 10;
}

/**
 * The values an axis names, from 0 to the largest value or just past it, at a round step
 * (1, 2, 2.5 or 5 times a power of ten): `niceTicks(0.023)` is 0, 0.01, 0.02, 0.03.
 */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0];
  const rough = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step =
    [1, 2, 2.5, 5, 10].map((times) => times * magnitude).find((s) => s >= rough) ?? rough;
  const steps = Math.ceil(max / step - 1e-9);
  return Array.from({ length: steps + 1 }, (_, index) => Number((index * step).toPrecision(12)));
}

/** Where the points of a chart stand across its plot, evenly, and the point nearest a position. */
export interface XScale {
  at: (index: number) => number;
  nearest: (position: number) => number;
}

/** The scale of `count` points over a plot from `left`, `width` wide. */
export function xScale(count: number, left: number, width: number): XScale {
  const step = count > 1 ? width / (count - 1) : 0;
  return {
    at: (index) => (count > 1 ? left + index * step : left + width / 2),
    nearest: (position) =>
      step > 0 ? Math.min(count - 1, Math.max(0, Math.round((position - left) / step))) : 0,
  };
}

/** The path of a line through the values, broken where one is missing. */
export function linePath(
  values: readonly (number | null)[],
  x: (index: number) => number,
  y: (value: number) => number,
): string {
  let path = "";
  let drawing = false;
  values.forEach((value, index) => {
    if (value === null) {
      drawing = false;
      return;
    }
    path += `${drawing ? "L" : "M"}${rounded(x(index))} ${rounded(y(value))}`;
    drawing = true;
  });
  return path;
}

/** The area between the line and the baseline, each run of values closed apart. */
export function areaPath(
  values: readonly (number | null)[],
  x: (index: number) => number,
  y: (value: number) => number,
  baseline: number,
): string {
  let path = "";
  let run: number[] = [];
  const close = () => {
    const first = run[0];
    const last = run.at(-1);
    if (first !== undefined && last !== undefined) {
      const line = run
        .map(
          (index, at) =>
            `${at === 0 ? "M" : "L"}${rounded(x(index))} ${rounded(y(values[index] ?? 0))}`,
        )
        .join("");
      path += `${line}L${rounded(x(last))} ${rounded(baseline)}L${rounded(x(first))} ${rounded(baseline)}Z`;
    }
    run = [];
  };
  values.forEach((value, index) => {
    if (value === null) close();
    else run.push(index);
  });
  close();
  return path;
}
