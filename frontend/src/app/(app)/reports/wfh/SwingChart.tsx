import type { HealthOfficeReportMetric } from "@/lib/api/types";

/**
 * Biggest swings: a compact grouped bar per metric, WFH/office/weekend side
 * by side.
 *
 * Bars are baseline-anchored at zero on purpose rather than scaled to the
 * three values' own range - a truncated axis is the standard way a bar chart
 * exaggerates a difference, and the swing badge already states the relative
 * difference precisely, so the bars themselves stay honest.
 *
 * Colour is fixed per bucket across every row on the page - WFH, office and
 * weekend mean the same colour whichever metric you're looking at.
 */

export const BUCKETS: ReadonlyArray<{ key: "wfh" | "office" | "weekend"; label: string; colour: string }> = [
  { key: "wfh", label: "WFH", colour: "var(--viz-1)" },
  { key: "office", label: "Office", colour: "var(--viz-2)" },
  { key: "weekend", label: "Weekend", colour: "var(--viz-6)" },
];

export function DayTypeLegend() {
  return (
    <ul className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-dim">
      {BUCKETS.map((bucket) => (
        <li key={bucket.key} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block size-2.5 rounded-full"
            style={{ backgroundColor: bucket.colour }}
          />
          {bucket.label}
        </li>
      ))}
    </ul>
  );
}

export function fmtMetricValue(value: number, unit: string): string {
  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded.toLocaleString()}${unit ? ` ${unit}` : ""}`;
}

/** The bucket a metric's own `direction` calls best, or null when it has none. */
export function bestBucket(
  metric: Pick<HealthOfficeReportMetric, "direction" | "wfh" | "office" | "weekend">,
): "wfh" | "office" | "weekend" | null {
  if (!metric.direction) return null;
  const better = metric.direction === "up" ? (a: number, b: number) => a > b : (a: number, b: number) => a < b;
  return BUCKETS.reduce<{ key: "wfh" | "office" | "weekend"; value: number } | null>((best, bucket) => {
    const value = metric[bucket.key];
    if (value === null || value === undefined) return best;
    if (!best || better(value, best.value)) return { key: bucket.key, value };
    return best;
  }, null)?.key ?? null;
}

export function SwingRow({ metric }: { metric: HealthOfficeReportMetric }) {
  const values = BUCKETS.map((bucket) => metric[bucket.key]).filter(
    (value): value is number => value !== null && value !== undefined,
  );
  const max = Math.max(...values, 0.0001);
  const best = bestBucket(metric);

  return (
    <div className="py-2.5">
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-ink">{metric.label}</p>
        {metric.swing_pct !== null && metric.swing_pct !== undefined && (
          <p className="text-xs text-ink-muted" title="Spread across buckets, as a share of their overall mean">
            ±{Math.round(metric.swing_pct)}%
          </p>
        )}
      </div>
      <div className="space-y-1">
        {BUCKETS.map((bucket) => {
          const value = metric[bucket.key];
          if (value === null || value === undefined) return null;
          const width = Math.max(4, (value / max) * 100);
          const isBest = best === bucket.key;
          return (
            <div key={bucket.key} className="flex items-center gap-2">
              <span className="w-14 shrink-0 text-xs text-ink-dim">{bucket.label}</span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${width}%`, backgroundColor: bucket.colour }}
                  title={`${bucket.label}: ${fmtMetricValue(value, metric.unit)}`}
                />
              </div>
              <span
                className={`w-20 shrink-0 text-right text-xs tabular-nums ${
                  isBest ? "font-semibold text-ink" : "text-ink-dim"
                }`}
              >
                {fmtMetricValue(value, metric.unit)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
