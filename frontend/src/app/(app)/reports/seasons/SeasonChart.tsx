import type { HealthSeasonReportMetric } from "@/lib/api/types";

import { ticks } from "../../charts";

/**
 * The Seasons report's card grid - same design as `../wfh/SwingChart.tsx`,
 * duplicated rather than shared because the two reports bucket by a
 * different number of categories with different field names on the wire
 * (`wfh`/`office`/`weekend` vs `summer`/`autumn`/`winter`/`spring`), and
 * threading that through one generic component would cost more in type
 * gymnastics than the ~250 lines it would save. See that file for the
 * reasoning behind the layout itself and each chart type's threshold.
 *
 * Southern Hemisphere colours: warm for the warm seasons, cool for the cold
 * one, green for spring - see `_SEASON_BY_MONTH` on the backend for why the
 * hemisphere matters here at all.
 */

export const BUCKETS: ReadonlyArray<{
  key: "summer" | "autumn" | "winter" | "spring";
  label: string;
  colour: string;
}> = [
  { key: "summer", label: "Summer", colour: "var(--viz-4)" },
  { key: "autumn", label: "Autumn", colour: "var(--viz-2)" },
  { key: "winter", label: "Winter", colour: "var(--viz-1)" },
  { key: "spring", label: "Spring", colour: "var(--viz-6)" },
];

export function fmtMetricValue(value: number, unit: string): string {
  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded.toLocaleString()}${unit ? ` ${unit}` : ""}`;
}

type BucketKey = (typeof BUCKETS)[number]["key"];

function rankedBucket(
  metric: Pick<HealthSeasonReportMetric, "direction" | "summer" | "autumn" | "winter" | "spring">,
  better: (a: number, b: number) => boolean,
): BucketKey | null {
  if (!metric.direction) return null;
  return BUCKETS.reduce<{ key: BucketKey; value: number } | null>((best, bucket) => {
    const value = metric[bucket.key];
    if (value === null || value === undefined) return best;
    if (!best || better(value, best.value)) return { key: bucket.key, value };
    return best;
  }, null)?.key ?? null;
}

/** The bucket a metric's own `direction` calls best, or null when it has none. */
export function bestBucket(
  metric: Pick<HealthSeasonReportMetric, "direction" | "summer" | "autumn" | "winter" | "spring">,
): BucketKey | null {
  return rankedBucket(metric, metric.direction === "up" ? (a, b) => a > b : (a, b) => a < b);
}

/** The mirror of `bestBucket` - the one the metric's direction calls worst. */
export function worstBucket(
  metric: Pick<HealthSeasonReportMetric, "direction" | "summer" | "autumn" | "winter" | "spring">,
): BucketKey | null {
  return rankedBucket(metric, metric.direction === "up" ? (a, b) => a < b : (a, b) => a > b);
}

function average(metric: HealthSeasonReportMetric): number | null {
  const values = BUCKETS.map((b) => metric[b.key]).filter(
    (v): v is number => v !== null && v !== undefined,
  );
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function totalDays(metric: HealthSeasonReportMetric): number {
  return metric.summer_days + metric.autumn_days + metric.winter_days + metric.spring_days;
}

// One small SVG per card - see `../wfh/SwingChart.tsx` for why these don't
// reuse the wide charts on `../../charts.tsx`.
const W = 200;
const H = 108;
const PAD_TOP = 14;
const PAD_BOTTOM = 20;
// Wider than the y-axis label column (`LABEL_X`) needs, on purpose: the first
// bucket sits at `PAD_SIDE`, and a bar half-width either side of that would
// otherwise reach back over the label it shares a row with.
const PAD_SIDE = 34;
const LABEL_X = 20;
const PLOT_H = H - PAD_TOP - PAD_BOTTOM;

/**
 * A y-axis tick, kept to a handful of characters regardless of the metric's
 * own scale. See `../wfh/SwingChart.tsx`'s `axisTick` - a label wider than
 * this column doesn't get clipped by its card, it draws past the SVG's own
 * left edge and disappears entirely.
 */
function axisTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 10_000) return `${Math.round(value / 1000)}k`;
  if (abs >= 1000) return `${Math.round((value / 1000) * 10) / 10}k`;
  if (abs >= 100) return Math.round(value).toLocaleString();
  return (Math.round(value * 10) / 10).toString();
}

function slotX(index: number): number {
  const usable = W - PAD_SIDE * 2;
  return PAD_SIDE + (usable / (BUCKETS.length - 1)) * index;
}

function presentPoints(metric: HealthSeasonReportMetric) {
  return BUCKETS.map((bucket, index) => ({ bucket, x: slotX(index), value: metric[bucket.key] })).filter(
    (p): p is { bucket: (typeof BUCKETS)[number]; x: number; value: number } =>
      p.value !== null && p.value !== undefined,
  );
}

function CategoryLabels() {
  return (
    <>
      {BUCKETS.map((bucket, index) => (
        <text
          key={bucket.key}
          x={slotX(index)}
          y={H - 4}
          textAnchor="middle"
          fontSize={9}
          fill="var(--viz-muted)"
        >
          {bucket.label}
        </text>
      ))}
    </>
  );
}

/**
 * A scatter of one dot per bucket, scaled to the buckets' own min/max.
 * See `../wfh/SwingChart.tsx`'s `MetricDots` for the reasoning.
 */
function MetricDots({ metric }: { metric: HealthSeasonReportMetric }) {
  const points = presentPoints(metric);
  if (points.length === 0) return null;

  const values = points.map((p) => p.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || Math.max(Math.abs(max), 1) * 0.1;
  const y = (v: number) => PAD_TOP + PLOT_H - ((v - min) / span) * PLOT_H;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label={`${metric.label} by season, ${points
        .map((p) => `${p.bucket.label} ${fmtMetricValue(p.value, metric.unit)}`)
        .join(", ")}`}
    >
      {[max, min].map((tick) => (
        <g key={tick}>
          <line
            x1={PAD_SIDE}
            x2={W - PAD_SIDE}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--viz-grid)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
          <text
            x={LABEL_X}
            y={y(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            fontSize={9}
            fill="var(--viz-muted)"
          >
            {axisTick(tick)}
          </text>
        </g>
      ))}
      {points.map((p) => (
        <circle key={p.bucket.key} cx={p.x} cy={y(p.value)} r={5} fill={p.bucket.colour}>
          <title>{`${p.bucket.label}: ${fmtMetricValue(p.value, metric.unit)}`}</title>
        </circle>
      ))}
      <CategoryLabels />
    </svg>
  );
}

/**
 * A baseline-anchored bar per bucket. See `../wfh/SwingChart.tsx`'s
 * `MetricBars` for the reasoning.
 */
function MetricBars({ metric }: { metric: HealthSeasonReportMetric }) {
  const points = presentPoints(metric);
  if (points.length === 0) return null;

  const rawMax = Math.max(...points.map((p) => p.value), 0.0001);
  const axisTicks = ticks(0, rawMax, 3);
  const max = axisTicks[axisTicks.length - 1] ?? rawMax;
  const y0 = H - PAD_BOTTOM;
  const barY = (v: number) => y0 - (v / max) * PLOT_H;
  // Four bars per card rather than three, so each gets a touch less width
  // than the WFH report's - otherwise adjacent bars would nearly touch.
  const barWidth = 18;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label={`${metric.label} by season, ${points
        .map((p) => `${p.bucket.label} ${fmtMetricValue(p.value, metric.unit)}`)
        .join(", ")}`}
    >
      <line
        x1={PAD_SIDE}
        x2={W - PAD_SIDE}
        y1={y0}
        y2={y0}
        stroke="var(--viz-grid)"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
      <text x={LABEL_X} y={PAD_TOP} textAnchor="end" dominantBaseline="hanging" fontSize={9} fill="var(--viz-muted)">
        {axisTick(max)}
      </text>
      <text x={LABEL_X} y={y0} textAnchor="end" dominantBaseline="middle" fontSize={9} fill="var(--viz-muted)">
        0
      </text>
      {points.map((p) => (
        <rect
          key={p.bucket.key}
          x={p.x - barWidth / 2}
          y={barY(p.value)}
          width={barWidth}
          height={Math.max(0, y0 - barY(p.value))}
          rx={3}
          fill={p.bucket.colour}
        >
          <title>{`${p.bucket.label}: ${fmtMetricValue(p.value, metric.unit)}`}</title>
        </rect>
      ))}
      <CategoryLabels />
    </svg>
  );
}

//: See `../wfh/SwingChart.tsx`'s `DOT_CHART_SWING_THRESHOLD`.
const DOT_CHART_SWING_THRESHOLD = 20;

export function MetricCard({ metric }: { metric: HealthSeasonReportMetric }) {
  const avg = average(metric);
  const days = totalDays(metric);
  const best = bestBucket(metric);
  const worst = worstBucket(metric);
  const useDots = metric.swing_pct !== null && metric.swing_pct !== undefined
    && metric.swing_pct < DOT_CHART_SWING_THRESHOLD;

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-0.5 flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">{metric.label}</h3>
        {avg !== null && (
          <span className="shrink-0 text-xs text-ink-muted">avg {fmtMetricValue(avg, metric.unit)}</span>
        )}
      </div>
      <p className="mb-2 text-xs text-ink-muted">
        {days.toLocaleString()} day{days === 1 ? "" : "s"}
      </p>

      {useDots ? <MetricDots metric={metric} /> : <MetricBars metric={metric} />}

      <p className="mt-1 text-xs">
        {best ? (
          <>
            <span className="text-emerald-600 dark:text-emerald-400">
              ▲ {BUCKETS.find((b) => b.key === best)!.label} best
            </span>
            {worst && worst !== best && (
              <>
                {" · "}
                <span className="text-amber-600 dark:text-amber-400">
                  ▼ {BUCKETS.find((b) => b.key === worst)!.label} worst
                </span>
              </>
            )}
          </>
        ) : (
          <span className="text-ink-muted">not ranked — no better direction for this one</span>
        )}
      </p>
    </div>
  );
}
