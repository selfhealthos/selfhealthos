import type { HealthOfficeReportMetric } from "@/lib/api/types";

import { ticks, tickLabel } from "../../charts";

/**
 * One card per metric: a title, an "avg" badge, a small chart, and a footer
 * naming which day type came out best (and worst, when there's a worse one
 * worth naming). Colour is fixed per bucket across every card on the page -
 * WFH, office and weekend mean the same colour whichever metric you're
 * looking at, matching the *fitcypher* dashboard this layout is drawn from.
 */

export const BUCKETS: ReadonlyArray<{ key: "wfh" | "office" | "weekend"; label: string; colour: string }> = [
  { key: "wfh", label: "WFH", colour: "var(--viz-2)" },
  { key: "office", label: "Office", colour: "var(--viz-3)" },
  // Weekend deliberately isn't a "real" colour slot - it's the day type this
  // report doesn't have an opinion about, so it gets the neutral grey already
  // used elsewhere for "not the point of the chart" rather than a third hue.
  { key: "weekend", label: "Weekend", colour: "var(--viz-stage-awake)" },
];

export function fmtMetricValue(value: number, unit: string): string {
  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded.toLocaleString()}${unit ? ` ${unit}` : ""}`;
}

type BucketKey = (typeof BUCKETS)[number]["key"];

function rankedBucket(
  metric: Pick<HealthOfficeReportMetric, "direction" | "wfh" | "office" | "weekend">,
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
  metric: Pick<HealthOfficeReportMetric, "direction" | "wfh" | "office" | "weekend">,
): BucketKey | null {
  return rankedBucket(metric, metric.direction === "up" ? (a, b) => a > b : (a, b) => a < b);
}

/** The mirror of `bestBucket` - the one the metric's direction calls worst. */
export function worstBucket(
  metric: Pick<HealthOfficeReportMetric, "direction" | "wfh" | "office" | "weekend">,
): BucketKey | null {
  return rankedBucket(metric, metric.direction === "up" ? (a, b) => a < b : (a, b) => a > b);
}

function average(metric: HealthOfficeReportMetric): number | null {
  const values = BUCKETS.map((b) => metric[b.key]).filter(
    (v): v is number => v !== null && v !== undefined,
  );
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function totalDays(metric: HealthOfficeReportMetric): number {
  return metric.wfh_days + metric.office_days + metric.weekend_days;
}

// One small SVG per card rather than the wide, axis-heavy charts elsewhere on
// the site (see `../../charts.tsx`) - these sit three-plus to a row, so every
// pixel of chrome competes with the next card's.
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

function slotX(index: number): number {
  const usable = W - PAD_SIDE * 2;
  return PAD_SIDE + (usable / (BUCKETS.length - 1)) * index;
}

function presentPoints(metric: HealthOfficeReportMetric) {
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
 * A scatter of one dot per bucket, scaled to the buckets' own min/max rather
 * than to zero.
 *
 * Used when the buckets are close together relative to their scale - a
 * baseline-anchored bar chart would draw three nearly-identical columns and
 * hide the very difference the card exists to show. `swing_pct` already
 * measures exactly this (see `office_report`), so the same number that ranks
 * "biggest swings" also decides which chart a metric gets.
 */
function MetricDots({ metric }: { metric: HealthOfficeReportMetric }) {
  const points = presentPoints(metric);
  if (points.length === 0) return null;

  const values = points.map((p) => p.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  // A flat line (every bucket equal) has no span to divide by - treat it as a
  // tiny one centred on the value rather than crashing or collapsing to a point.
  const span = max - min || Math.max(Math.abs(max), 1) * 0.1;
  const y = (v: number) => PAD_TOP + PLOT_H - ((v - min) / span) * PLOT_H;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label={`${metric.label} by day type, ${points
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
            {tickLabel(tick)}
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
 * A baseline-anchored bar per bucket - the honest default whenever the
 * buckets differ by enough that zero is a fair place to start from.
 */
function MetricBars({ metric }: { metric: HealthOfficeReportMetric }) {
  const points = presentPoints(metric);
  if (points.length === 0) return null;

  const rawMax = Math.max(...points.map((p) => p.value), 0.0001);
  const axisTicks = ticks(0, rawMax, 3);
  const max = axisTicks[axisTicks.length - 1] ?? rawMax;
  const y0 = H - PAD_BOTTOM;
  const barY = (v: number) => y0 - (v / max) * PLOT_H;
  const barWidth = 22;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label={`${metric.label} by day type, ${points
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
        {tickLabel(max)}
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

//: Below this, a 0-based bar chart would draw three columns close enough in
//: height to look identical - the buckets differ, but not on a scale zero
//: has anything to say about. Above it, the columns' own heights carry the
//: comparison better than a zoomed axis would.
const DOT_CHART_SWING_THRESHOLD = 20;

export function MetricCard({ metric }: { metric: HealthOfficeReportMetric }) {
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
