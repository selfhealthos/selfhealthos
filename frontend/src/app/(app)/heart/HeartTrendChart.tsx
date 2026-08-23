import { Crosshair, type CrosshairColumn } from "../Crosshair";

/**
 * The recovery view's master chart: HRV and resting heart rate, one plot.
 *
 * **One axis, two units, and the page says so.** RMSSD in milliseconds and
 * resting heart rate in bpm are different measurements that happen to occupy
 * the same numeric range - roughly 20-80 and 50-70 - so they can share a scale
 * without either being squashed. This is the same exception the sleep master
 * chart takes, and it holds for the same reason: the series genuinely live in
 * the same space, so their crossings are real rather than an artefact of
 * scaling. One gridline is ten milliseconds and ten beats at once.
 *
 * **What a shared axis cannot say is direction**, and here the two disagree:
 * HRV rising is good, resting heart rate rising is not. Two lines converging
 * therefore has no single meaning, which is exactly the reading a shared axis
 * invites. So the direction travels with each series from the API and is
 * printed in the legend, and a series moving the good way is annotated as
 * such at its last point.
 *
 * **The bands are the point.** Neither number means much in absolute terms -
 * `scoring.py` says as much in HRV's own evidence string - so each series is
 * drawn over its own trailing-month mean ±1 SD. A point inside the band is an
 * ordinary day; a run of points below it is the signal people actually watch
 * for. Without the band this chart is two wiggly lines and a number nobody has
 * a reference for.
 */

export type TrendSeries = {
  metric: string;
  label: string;
  unit: string;
  /** "up" or "down" - which way is the good way. */
  direction: string;
  points: Array<{ date: string; value: number }>;
  //: Optional as well as nullable: the generated API types express a field
  //: with a default that way, and both mean the same thing here - too few
  //: readings to have a usual range.
  baseline?: { mean: number; sd: number; low: number; high: number; days: number } | null;
  colour: string;
};

const W = 1200;
const PAD = { top: 18, right: 66, bottom: 0, left: 46 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = 440;
const AXIS_H = 26;
const STEP = 10;

function dayNumber(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1) / 86_400_000;
}

function shortLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)).toLocaleDateString("en-AU", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** Label every Nth day, where N keeps the axis to about a dozen ticks. */
function dateStep(days: number): number {
  return [1, 2, 3, 7, 14, 30].find((step) => days / step <= 12) ?? 60;
}

/**
 * Split a series wherever it stops being daily.
 *
 * A fortnight the watch was not worn comes back as two clusters, and joining
 * them draws a confident line across days nobody measured - the same rule
 * every other chart in this app follows.
 */
function runs(points: Array<{ date: string; value: number }>, limitDays = 3) {
  const out: Array<Array<{ date: string; value: number }>> = [];
  let current: Array<{ date: string; value: number }> = [];
  points.forEach((point, index) => {
    const previous = points[index - 1];
    if (previous && dayNumber(point.date) - dayNumber(previous.date) > limitDays) {
      out.push(current);
      current = [];
    }
    current.push(point);
  });
  if (current.length) out.push(current);
  return out.filter((chunk) => chunk.length > 0);
}

export function HeartTrendChart({
  series,
  start,
  end,
}: {
  series: TrendSeries[];
  /** The window, not the data: an unworn week should read as a gap. */
  start: string;
  end: string;
}) {
  const drawable = series.filter((one) => one.points.length > 0);
  if (drawable.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        No HRV or resting heart rate recorded in this window.
      </p>
    );
  }

  const x0 = dayNumber(start);
  const x1 = dayNumber(end);
  const span = x1 - x0 || 1;
  const height = PAD.top + PLOT_H + AXIS_H;

  const slotWidth = PLOT_W / (span + 1);
  const x = (iso: string) => PAD.left + (dayNumber(iso) - x0) * slotWidth + slotWidth / 2;

  // Cropped to the data plus its bands, on the 10-unit grid, rather than run
  // from zero. Both series live between about 30 and 70, so a zero baseline
  // spends the bottom third of a master chart on a region neither line will
  // ever visit - and the whole reason this chart is the size it is, is to make
  // a 5 ms move visible. The usual objection to a non-zero baseline is that it
  // exaggerates; it applies to bars, whose length encodes the value, and not
  // to these, where the reference is the shaded band rather than the axis.
  const spread = drawable.flatMap((one) => [
    ...one.points.map((point) => point.value),
    one.baseline?.low ?? Infinity,
    one.baseline?.high ?? -Infinity,
  ]);
  const yMin = Math.max(0, Math.floor((Math.min(...spread) - 5) / STEP) * STEP);
  const yMax = Math.ceil((Math.max(...spread) + 5) / STEP) * STEP;
  const y = (value: number) =>
    PAD.top + PLOT_H - ((value - yMin) / (yMax - yMin || 1)) * PLOT_H;

  const gridlines: number[] = [];
  for (let value = yMin; value <= yMax; value += STEP) gridlines.push(value);

  const step = dateStep(span + 1);
  const dateTicks: string[] = [];
  for (let day = x0; day <= x1; day += step) {
    dateTicks.push(new Date(day * 86_400_000).toISOString().slice(0, 10));
  }

  // Every date holding any reading is a crosshair column, so the tooltip can
  // answer "what were both of these doing that day" in one hover.
  const lookup = drawable.map((one) => new Map(one.points.map((p) => [p.date, p.value])));
  const dates = [...new Set(drawable.flatMap((one) => one.points.map((p) => p.date)))].sort();
  const columns: CrosshairColumn[] = dates.map((date) => ({
    at: x(date) / W,
    title: shortLabel(date),
    rows: drawable.map((one, index) => {
      const value = lookup[index]?.get(date);
      const baseline = one.baseline;
      const state =
        value === undefined || !baseline
          ? ""
          : value > baseline.high
            ? " ↑ above usual"
            : value < baseline.low
              ? " ↓ below usual"
              : " · usual";
      return {
        label: one.label,
        value: value === undefined ? "—" : `${Math.round(value)} ${one.unit}${state}`,
        colour: one.colour,
      };
    }),
  }));

  return (
    <Crosshair columns={columns}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`HRV and resting heart rate from ${start} to ${end}, each shaded with its own trailing-month normal range`}
      >
        {/* Baselines behind the grid: they are ground, and a gridline crossing
            one should still be readable. */}
        {drawable.map((one) =>
          one.baseline ? (
            <g key={`band-${one.metric}`}>
              <rect
                x={PAD.left}
                y={y(one.baseline.high)}
                width={PLOT_W}
                height={Math.max(1, y(one.baseline.low) - y(one.baseline.high))}
                fill={one.colour}
                fillOpacity={0.1}
              >
                <title>
                  {`${one.label}: usual range ${Math.round(one.baseline.low)}–${Math.round(
                    one.baseline.high,
                  )} ${one.unit} over the last ${one.baseline.days} days`}
                </title>
              </rect>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(one.baseline.mean)}
                y2={y(one.baseline.mean)}
                stroke={one.colour}
                strokeWidth={1}
                strokeDasharray="4 5"
                strokeOpacity={0.6}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          ) : null,
        )}

        {gridlines.map((value) => (
          <g key={value}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={PAD.left - 8}
              y={y(value)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {value}
            </text>
          </g>
        ))}

        {dateTicks.map((tick) => (
          <line
            key={tick}
            x1={x(tick)}
            x2={x(tick)}
            y1={PAD.top}
            y2={PAD.top + PLOT_H}
            stroke="var(--viz-grid)"
            strokeWidth={1}
            strokeOpacity={0.7}
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {drawable.map((one) => {
          const chunks = runs(one.points);
          return chunks.map((chunk, chunkIndex) => {
            const d = chunk
              .map(
                (point, index) =>
                  `${index === 0 ? "M" : "L"}${x(point.date).toFixed(1)},${y(point.value).toFixed(1)}`,
              )
              .join(" ");
            const last = chunk[chunk.length - 1];
            return (
              <g key={`${one.metric}-${chunkIndex}`}>
                <path
                  d={d}
                  fill="none"
                  stroke="var(--viz-surface)"
                  strokeWidth={5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  strokeOpacity={0.85}
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d={d}
                  fill="none"
                  stroke={one.colour}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
                {/* Each point marked, because with a baseline band behind it
                    the question is "which side of the band is this day on",
                    and that is asked of individual days. */}
                {chunk.map((point) => (
                  <circle
                    key={point.date}
                    cx={x(point.date)}
                    cy={y(point.value)}
                    r={2}
                    fill={one.colour}
                  />
                ))}
                {chunkIndex === chunks.length - 1 && last && (
                  <text
                    x={Math.min(W - PAD.right + 6, x(last.date) + 8)}
                    y={y(last.value) - 6}
                    fontSize={11}
                    fill={one.colour}
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {Math.round(last.value)} {one.unit}
                  </text>
                )}
              </g>
            );
          });
        })}

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={PAD.top + PLOT_H}
          y2={PAD.top + PLOT_H}
          stroke="var(--viz-axis)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
        {dateTicks.map((tick) => (
          <text
            key={tick}
            x={x(tick)}
            y={height - 8}
            textAnchor="middle"
            fontSize={11}
            fill="var(--viz-muted)"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {shortLabel(tick)}
          </text>
        ))}
      </svg>
    </Crosshair>
  );
}

/**
 * The legend, which this chart cannot do without.
 *
 * Two units on one axis is only honest if the units are named, and two series
 * that want opposite directions is only honest if the directions are named.
 */
export function TrendLegend({ series }: { series: TrendSeries[] }) {
  return (
    <div className="mb-3 space-y-1.5 text-xs text-slate-500 dark:text-slate-400">
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {series.map((one) => (
          <li key={one.metric} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="h-0.5 w-4 rounded-full"
              style={{ backgroundColor: one.colour }}
            />
            {one.label} <span className="text-slate-400 dark:text-slate-600">{one.unit}</span>
            <span className="text-slate-400 dark:text-slate-600">
              {one.direction === "up" ? "· higher is better" : "· lower is better"}
            </span>
          </li>
        ))}
      </ul>
      <p>
        Each shaded band is that signal&rsquo;s own usual range — its mean and one standard
        deviation over the last 30 days. Inside the band is an ordinary day; a run of days outside
        it is the thing worth noticing.
      </p>
    </div>
  );
}
