/**
 * Charts for the Health app: plain SVG, rendered on the server.
 *
 * **Why no charting library.** The roadmap penciled in Recharts. It is the
 * wrong fit here for two reasons that only became clear once the pages were
 * laid out: every chart on these pages is a static picture of a server-fetched
 * series, and Recharts is a client component - adopting it turns thirteen
 * server-rendered pages into thirteen hydrated ones to gain interactivity that
 * a `<title>` element already provides. The second reason is that the frontend
 * has exactly three runtime dependencies today (`next`, `react`, `react-dom`),
 * which is a property worth more than a bar chart. If a chart ever needs
 * brushing, zooming or live updates, that chart gets a library and the rest of
 * these stay as they are.
 *
 * **Colour** comes from the `--viz-*` custom properties in `globals.css`, in
 * fixed slot order, never cycled. The rules those follow - and what to re-run
 * before changing one - are documented there.
 *
 * **The hover layer** is an SVG `<title>` per mark. The browser renders it as a
 * tooltip natively, so a chart is inspectable without a byte of JavaScript.
 * Every chart also ships a legend when it has two or more series, and every
 * page carries the same numbers as a table underneath.
 */

const SLOTS = [
  "var(--viz-1)",
  "var(--viz-2)",
  "var(--viz-3)",
  "var(--viz-4)",
  "var(--viz-5)",
  "var(--viz-6)",
  "var(--viz-7)",
  "var(--viz-8)",
] as const;

/** Slot `index`, clamped. Never wraps: a ninth series is a design error, and
 *  silently repainting it as slot 1 hides that from the person reading it. */
export function slot(index: number): string {
  return SLOTS[Math.min(index, SLOTS.length - 1)]!;
}

export const SEQUENTIAL = [
  "var(--viz-seq-1)",
  "var(--viz-seq-2)",
  "var(--viz-seq-3)",
  "var(--viz-seq-4)",
  "var(--viz-seq-5)",
  "var(--viz-seq-6)",
] as const;

export type SeriesPoint = { date: string; value: number };
export type Series = { label: string; points: SeriesPoint[]; unit?: string };

// The viewBox is a fixed coordinate space; the SVG scales to its container.
// Chosen wide because these sit in a content column, not a dashboard tile.
export const W = 720;
const H = 220;
export const PAD = { top: 12, right: 52, bottom: 22, left: 44 };
export const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

function dayNumber(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1) / 86_400_000;
}

/** Round tick values to something a person would say out loud. */
export function ticks(min: number, max: number, count = 4): number[] {
  const span = max - min || 1;
  const rough = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? magnitude;
  const out: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step / 1000; t += step) out.push(t);
  return out;
}

export function tickLabel(value: number): string {
  if (Math.abs(value) >= 10_000) return `${Math.round(value / 1000)}k`;
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1);
}

function monthLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)).toLocaleDateString("en-AU", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/**
 * Split a series wherever it stops being continuous.
 *
 * A metric the watch did not record for a fortnight comes back from the API as
 * two clusters of points with nothing between them. Joining them draws a
 * straight, confident line across a gap where there is no data at all - the
 * most quietly dishonest thing a line chart can do.
 *
 * The threshold is relative, not a fixed number of days: three times the median
 * interval. Daily data breaks after ~3 missing days, a monthly measurement
 * survives its normal spacing, and neither needs to be configured.
 */
function segments(points: SeriesPoint[]): SeriesPoint[][] {
  if (points.length < 2) return points.length ? [points] : [];
  const gaps = points
    .slice(1)
    .map((p, i) => dayNumber(p.date) - dayNumber(points[i]!.date))
    .sort((a, b) => a - b);
  const median = gaps[Math.floor(gaps.length / 2)] ?? 1;
  const limit = Math.max(median * 3, 2);

  const out: SeriesPoint[][] = [[points[0]!]];
  for (let i = 1; i < points.length; i++) {
    const gap = dayNumber(points[i]!.date) - dayNumber(points[i - 1]!.date);
    if (gap > limit) out.push([]);
    out[out.length - 1]!.push(points[i]!);
  }
  return out.filter((s) => s.length > 0);
}

export function Legend({
  items,
}: {
  items: ReadonlyArray<{ label: string; color: string }>;
}) {
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
          {/* Identity lives in the swatch, never in the text colour - a light
              categorical hue is illegible as text on the surface. */}
          <span
            aria-hidden
            className="h-0.5 w-4 rounded-full"
            style={{ backgroundColor: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/**
 * One or more daily series over a shared date axis.
 *
 * `zeroBased` is off by default and that is deliberate: a resting heart rate
 * plotted from zero is a flat line across the top of the box. Counts (steps,
 * minutes) pass it, levels (weight, HRV, BP) do not.
 */
export function LineChart({
  series,
  height = H,
  zeroBased = false,
  unit = "",
  reference,
  normalBand,
}: {
  series: Series[];
  height?: number;
  zeroBased?: boolean;
  unit?: string;
  /** A target line - a step goal, a blood-pressure threshold. */
  reference?: { value: number; label: string };
  /**
   * A clinical normal range, drawn as a shaded zone behind the line.
   *
   * Both edges join the y domain even when the data never reaches them. That
   * costs some vertical resolution and buys the only thing the band is for: a
   * line hugging the bottom of the normal range and a line comfortably inside
   * it look identical if the boundary is off-screen, and "95-100% is normal"
   * in the caption leaves the reader estimating where 95 falls on the axis.
   */
  normalBand?: { from: number; to: number; label: string };
}) {
  const all = series.flatMap((s) => s.points);
  if (all.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        Nothing recorded in this window.
      </p>
    );
  }

  const days = all.map((p) => dayNumber(p.date));
  const xMin = Math.min(...days);
  const xMax = Math.max(...days);
  const xSpan = xMax - xMin || 1;

  const values = all.map((p) => p.value);
  const candidates = [
    ...values,
    ...(reference ? [reference.value] : []),
    ...(normalBand ? [normalBand.from, normalBand.to] : []),
  ];
  const rawMin = zeroBased ? 0 : Math.min(...candidates);
  const rawMax = Math.max(...candidates);
  // A little headroom, so an extreme does not sit on the frame.
  const pad = (rawMax - rawMin || Math.abs(rawMax) || 1) * 0.08;
  const yMin = zeroBased ? 0 : rawMin - pad;
  const yMax = rawMax + pad;
  const ySpan = yMax - yMin || 1;

  const x = (iso: string) => PAD.left + ((dayNumber(iso) - xMin) / xSpan) * PLOT_W;
  const y = (value: number) => PAD.top + PLOT_H - ((value - yMin) / ySpan) * PLOT_H;

  const yTicks = ticks(yMin, yMax);
  const firstDate = all.reduce((a, b) => (a.date < b.date ? a : b)).date;
  const lastDate = all.reduce((a, b) => (a.date > b.date ? a : b)).date;

  return (
    <>
      {series.length > 1 && (
        <Legend items={series.map((s, i) => ({ label: s.label, color: slot(i) }))} />
      )}
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="w-full h-auto"
        role="img"
        aria-label={`${series.map((s) => s.label).join(", ")} from ${firstDate} to ${lastDate}`}
      >
        {/* The normal zone sits under everything, including the gridlines: it
            is context for the marks, and a band drawn over them competes with
            the data for the reader's attention. */}
        {normalBand && (
          <g>
            <rect
              x={PAD.left}
              y={y(Math.max(normalBand.from, normalBand.to))}
              width={PLOT_W}
              height={Math.abs(y(normalBand.from) - y(normalBand.to))}
              fill="var(--viz-normal-band)"
            />
            <text
              x={W - PAD.right - 4}
              y={y(Math.max(normalBand.from, normalBand.to)) + 11}
              textAnchor="end"
              fontSize={10}
              fill="var(--viz-muted)"
            >
              {normalBand.label}
            </text>
          </g>
        )}

        {/* Gridlines: hairline, solid, one step off the surface. Recessive. */}
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={PAD.left - 8}
              y={y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {tickLabel(tick)}
            </text>
          </g>
        ))}

        {reference && (
          <>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(reference.value)}
              y2={y(reference.value)}
              stroke="var(--viz-axis)"
              strokeWidth={1}
              strokeDasharray="4 3"
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={W - PAD.right + 4}
              y={y(reference.value)}
              dominantBaseline="middle"
              fontSize={10}
              fill="var(--viz-muted)"
            >
              {reference.label}
            </text>
          </>
        )}

        {series.map((s, index) => {
          const colour = slot(index);
          const last = s.points[s.points.length - 1];
          return (
            <g key={s.label}>
              {segments(s.points).map((run, runIndex) => (
                <path
                  key={runIndex}
                  d={run
                    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`)
                    .join(" ")}
                  fill="none"
                  stroke={colour}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              {/* An end marker with a surface ring, so it stays legible where
                  two series converge at the right edge. */}
              {last && (
                <circle
                  cx={x(last.date)}
                  cy={y(last.value)}
                  r={4}
                  fill={colour}
                  stroke="var(--viz-surface)"
                  strokeWidth={2}
                >
                  <title>{`${s.label}: ${last.value.toLocaleString()}${unit ? ` ${unit}` : ""} on ${last.date}`}</title>
                </circle>
              )}
              {/* Direct label on the endpoint only. A number on every point is
                  chaos and goes unread; the axis and the table carry the rest. */}
              {last && series.length <= 4 && (
                <text
                  x={x(last.date) + 8}
                  y={y(last.value)}
                  dominantBaseline="middle"
                  fontSize={11}
                  fill="var(--viz-muted)"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {tickLabel(last.value)}
                </text>
              )}
            </g>
          );
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
        <text x={PAD.left} y={height - 6} fontSize={11} fill="var(--viz-muted)">
          {monthLabel(firstDate)}
        </text>
        <text
          x={W - PAD.right}
          y={height - 6}
          textAnchor="end"
          fontSize={11}
          fill="var(--viz-muted)"
        >
          {monthLabel(lastDate)}
        </text>
      </svg>
    </>
  );
}

/**
 * Columns over a categorical or weekly axis.
 *
 * Bars are capped at 24px and always leave a 2px gap: the gap is what
 * separates neighbours, never a stroke around the mark.
 */
export function BarChart({
  bars,
  height = 180,
  unit = "",
  colour = "var(--viz-1)",
  reference,
}: {
  bars: ReadonlyArray<{ label: string; value: number; title?: string }>;
  height?: number;
  unit?: string;
  colour?: string;
  reference?: { value: number; label: string };
}) {
  if (bars.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        Nothing recorded in this window.
      </p>
    );
  }

  const plotH = height - PAD.top - PAD.bottom;
  const max = Math.max(...bars.map((b) => b.value), reference?.value ?? 0) || 1;
  const band = PLOT_W / bars.length;
  const width = Math.min(24, Math.max(2, band - 2));
  const y = (value: number) => PAD.top + plotH - (value / max) * plotH;
  const yTicks = ticks(0, max, 3);

  // Every label only fits on a short axis; past that, label the ends and let
  // the tooltips carry the rest. A clipped or overlapping label is worse than
  // no label.
  const labelEvery = Math.ceil(bars.length / 8);

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      className="w-full h-auto"
      role="img"
      aria-label={`${bars.length} bars, highest ${max.toLocaleString()}${unit ? ` ${unit}` : ""}`}
    >
      {yTicks.map((tick) => (
        <g key={tick}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--viz-grid)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
          <text
            x={PAD.left - 8}
            y={y(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            fontSize={11}
            fill="var(--viz-muted)"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {tickLabel(tick)}
          </text>
        </g>
      ))}

      {reference && (
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(reference.value)}
          y2={y(reference.value)}
          stroke="var(--viz-axis)"
          strokeWidth={1}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />
      )}

      {bars.map((bar, index) => {
        const top = y(bar.value);
        const barHeight = Math.max(0, PAD.top + plotH - top);
        return (
          <g key={`${bar.label}-${index}`}>
            {/* 4px rounded data-end, square at the baseline: the rect is drawn
                past the axis and clipped by the axis line above it. */}
            <rect
              x={PAD.left + index * band + (band - width) / 2}
              y={top}
              width={width}
              height={barHeight + 4}
              rx={4}
              fill={colour}
            >
              <title>{bar.title ?? `${bar.label}: ${bar.value.toLocaleString()}${unit ? ` ${unit}` : ""}`}</title>
            </rect>
            {index % labelEvery === 0 && (
              <text
                x={PAD.left + index * band + band / 2}
                y={height - 6}
                textAnchor="middle"
                fontSize={10}
                fill="var(--viz-muted)"
              >
                {bar.label}
              </text>
            )}
          </g>
        );
      })}

      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={PAD.top + plotH}
        y2={PAD.top + plotH}
        stroke="var(--viz-axis)"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/**
 * Columns over a date axis, optionally stacked.
 *
 * Used with one layer it is a plain column chart (steps per day); with several
 * it stacks them (sleep stages, Bristol scores). One component rather than two
 * because the axis, the density handling and the tooltips are the whole of the
 * work and they are identical either way.
 *
 * **Absent days are absent.** A day the watch recorded nothing leaves a hole in
 * the axis rather than closing ranks, so a fortnight of missing data looks like
 * a fortnight of missing data instead of compressing the surrounding days
 * together. A day whose total is genuinely zero draws nothing either - a
 * zero-height column is invisible whatever we intend - so the two are not
 * distinguishable here, and a chart where that distinction matters wants the
 * calendar heatmap instead, which has a cell for every day.
 */
export function StackedColumnChart({
  dates,
  layers,
  height = 200,
  unit = "",
  stackLabel,
  reference,
}: {
  /** Every date to plot, ascending. Gaps in this list are gaps in the chart. */
  dates: string[];
  /** Bottom of the stack first. */
  layers: ReadonlyArray<{ label: string; color: string; values: Record<string, number> }>;
  height?: number;
  unit?: string;
  /** Formats the tooltip's total, e.g. minutes into "7h 20m". */
  stackLabel?: (total: number) => string;
  reference?: { value: number; label: string };
}) {
  if (dates.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        Nothing recorded in this window.
      </p>
    );
  }

  const plotH = height - PAD.top - PAD.bottom;
  const totals = dates.map((date) =>
    layers.reduce((sum, layer) => sum + (layer.values[date] ?? 0), 0),
  );
  const max = Math.max(...totals, reference?.value ?? 0) || 1;

  // Columns are laid out by calendar position, not by array index, so a missing
  // day leaves a hole rather than closing the ranks and compressing the axis.
  const first = dayNumber(dates[0]!);
  const last = dayNumber(dates[dates.length - 1]!);
  const spanDays = last - first + 1;
  const band = PLOT_W / spanDays;
  // The 2px surface gap between neighbours only survives while there is room
  // for it; past roughly 200 columns it scales down rather than eating the mark.
  const gap = Math.min(2, band * 0.3);
  const width = Math.min(24, Math.max(1, band - gap));

  const y = (value: number) => PAD.top + plotH - (value / max) * plotH;
  const xOf = (date: string) => PAD.left + (dayNumber(date) - first) * band;

  return (
    <>
      {layers.length > 1 && (
        <Legend items={layers.map((layer) => ({ label: layer.label, color: layer.color }))} />
      )}
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="w-full h-auto"
        role="img"
        aria-label={`${layers.map((l) => l.label).join(", ")} per day from ${dates[0]} to ${dates[dates.length - 1]}`}
      >
        {ticks(0, max, 3).map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={PAD.left - 8}
              y={y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {tickLabel(tick)}
            </text>
          </g>
        ))}

        {reference && (
          <>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(reference.value)}
              y2={y(reference.value)}
              stroke="var(--viz-axis)"
              strokeWidth={1}
              strokeDasharray="4 3"
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={W - PAD.right + 4}
              y={y(reference.value)}
              dominantBaseline="middle"
              fontSize={10}
              fill="var(--viz-muted)"
            >
              {reference.label}
            </text>
          </>
        )}

        {dates.map((date, index) => {
          const total = totals[index]!;
          if (total <= 0) return null;
          const breakdown = layers
            .filter((layer) => (layer.values[date] ?? 0) > 0)
            .map((layer) => `${layer.label} ${tickLabel(layer.values[date]!)}`)
            .join(" · ");
          const tip =
            `${date} — ${stackLabel ? stackLabel(total) : `${tickLabel(total)}${unit ? ` ${unit}` : ""}`}` +
            (layers.length > 1 ? `\n${breakdown}` : "");

          // Only the layers that actually have a value, bottom of the stack
          // first. Filtered here rather than inside the map so that "first" and
          // "last" mean the visible bottom and top - otherwise an empty top
          // layer robs the real top segment of its rounded end.
          const present = layers
            .map((layer) => ({ layer, value: layer.values[date] ?? 0 }))
            .filter((row) => row.value > 0);
          const radius = Math.min(4, width / 2);

          // Geometry is computed bottom-up, because each segment sits on the
          // running total beneath it.
          let used = 0;
          const rects = present.map(({ layer, value }, index) => {
            const segmentH = (value / max) * plotH;
            const top = PAD.top + plotH - used - segmentH;
            used += segmentH;

            const isBottom = index === 0;
            const isTop = index === present.length - 1;

            // The 2px separation between touching segments is white doing the
            // work; a stroke around each one would add ink that is not data. It
            // comes off each segment's FOOT, never its head - off the head
            // instead would lift the whole stack off the baseline by one gap.
            //
            // `rx` rounds all four corners, so the top segment is drawn
            // `radius` taller and the curve at its foot is hidden - by the
            // segment beneath it, or by the axis line when it is the only one.
            // That is what keeps the data-end rounded and the baseline square.
            const foot = isBottom ? 0 : gap;
            const head = isTop ? radius : 0;

            return (
              <rect
                key={layer.label}
                x={xOf(date) + gap / 2}
                y={top}
                width={width}
                height={Math.max(0.5, segmentH - foot + head)}
                rx={isTop ? radius : 0}
                fill={layer.color}
              />
            );
          });

          // ...but painted top-down. The top segment's `radius` overhang has to
          // end up UNDER the segment below it; drawn in stacking order it would
          // paint over that segment and swallow the gap that separates them.
          return (
            <g key={date}>
              <title>{tip}</title>
              {rects.reverse()}
            </g>
          );
        })}

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={PAD.top + plotH}
          y2={PAD.top + plotH}
          stroke="var(--viz-axis)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
        <text x={PAD.left} y={height - 6} fontSize={11} fill="var(--viz-muted)">
          {monthLabel(dates[0]!)}
        </text>
        <text
          x={W - PAD.right}
          y={height - 6}
          textAnchor="end"
          fontSize={11}
          fill="var(--viz-muted)"
        >
          {monthLabel(dates[dates.length - 1]!)}
        </text>
      </svg>
    </>
  );
}

/**
 * A horizontal proportion bar - sleep stages, heart-rate zones.
 *
 * The 2px gaps are in the surface colour rather than transparent, so segments
 * stay separated over any background the card happens to have.
 */
export function StackedBar({
  segments: parts,
  className = "",
}: {
  segments: ReadonlyArray<{ label: string; value: number; color: string }>;
  className?: string;
}) {
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  if (total <= 0) return null;
  return (
    <div className={`flex h-3 gap-0.5 overflow-hidden rounded ${className}`}>
      {parts
        .filter((part) => part.value > 0)
        .map((part) => (
          <div
            key={part.label}
            style={{ width: `${(part.value / total) * 100}%`, backgroundColor: part.color }}
            title={`${part.label} ${Math.round(part.value)}`}
          />
        ))}
    </div>
  );
}

/**
 * A year of daily values as a calendar grid — one column per week.
 *
 * Sequential encoding: one hue, light to dark. A day with no data is drawn as
 * an empty cell in the grid colour, distinct from a day whose value is genuinely
 * zero, because "the watch was off" and "did not move" are different facts and
 * the same blank square for both is the most common lie in a heatmap.
 */
export function CalendarHeatmap({
  values,
  start,
  end,
  unit = "",
  emptyLabel = "no data",
}: {
  values: Record<string, number>;
  start: string;
  end: string;
  unit?: string;
  emptyLabel?: string;
}) {
  const startDay = dayNumber(start);
  const endDay = dayNumber(end);
  const present = Object.values(values);
  const max = present.length ? Math.max(...present) : 1;

  // Columns are weeks starting Monday. `dayNumber` counts from 1970-01-01, a
  // Thursday, so +3 rotates the week to start on Monday.
  const weekdayOf = (day: number) => (((day + 3) % 7) + 7) % 7;
  const firstColumnDay = startDay - weekdayOf(startDay);
  const weeks = Math.ceil((endDay - firstColumnDay + 1) / 7);

  const cell = 11;
  const gap = 2;
  const width = weeks * (cell + gap);
  const height = 7 * (cell + gap) + 14;

  const cells = [];
  for (let column = 0; column < weeks; column++) {
    for (let row = 0; row < 7; row++) {
      const day = firstColumnDay + column * 7 + row;
      if (day < startDay || day > endDay) continue;
      const iso = new Date(day * 86_400_000).toISOString().slice(0, 10);
      const value = values[iso];
      const step =
        value === undefined
          ? null
          : SEQUENTIAL[Math.min(SEQUENTIAL.length - 1, Math.floor((value / max) * SEQUENTIAL.length))];
      cells.push(
        <rect
          key={iso}
          x={column * (cell + gap)}
          y={row * (cell + gap)}
          width={cell}
          height={cell}
          rx={2}
          fill={step ?? "var(--viz-grid)"}
        >
          <title>
            {value === undefined
              ? `${iso} — ${emptyLabel}`
              : `${iso}: ${value.toLocaleString()}${unit ? ` ${unit}` : ""}`}
          </title>
        </rect>,
      );
    }
  }

  // Month ticks along the bottom, at the first column of each month.
  const months: React.ReactElement[] = [];
  let lastMonth = -1;
  for (let column = 0; column < weeks; column++) {
    const day = firstColumnDay + column * 7;
    if (day < startDay) continue;
    const at = new Date(day * 86_400_000);
    if (at.getUTCMonth() !== lastMonth) {
      lastMonth = at.getUTCMonth();
      months.push(
        <text
          key={`${at.getUTCFullYear()}-${lastMonth}`}
          x={column * (cell + gap)}
          y={height - 2}
          fontSize={10}
          fill="var(--viz-muted)"
        >
          {at.toLocaleDateString("en-AU", { month: "short", timeZone: "UTC" })}
        </text>,
      );
    }
  }

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label={`Daily values from ${start} to ${end}`}
      >
        {cells}
        {months}
      </svg>
    </div>
  );
}

/**
 * The intraday trace: one day of minute samples.
 *
 * Separate from `LineChart` because the x axis is a clock rather than a
 * calendar, and because 1,440 points want a thinner stroke and no end marker -
 * a dot on the last minute of the day means nothing.
 */
export function IntradayChart({
  points,
  timeZone,
  unit = "",
  colour = "var(--viz-8)",
}: {
  points: ReadonlyArray<{ at: string; value: number }>;
  timeZone: string;
  unit?: string;
  colour?: string;
}) {
  if (points.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        No minute-level samples for this day.
      </p>
    );
  }

  const height = 180;
  const plotH = height - PAD.top - PAD.bottom;
  const times = points.map((p) => new Date(p.at).getTime());
  const tMin = Math.min(...times);
  const tMax = Math.max(...times);
  const tSpan = tMax - tMin || 1;
  const values = points.map((p) => p.value);
  const vMin = Math.min(...values);
  const vMax = Math.max(...values);
  const vSpan = vMax - vMin || 1;

  const x = (t: number) => PAD.left + ((t - tMin) / tSpan) * PLOT_W;
  const y = (v: number) => PAD.top + plotH - ((v - vMin) / vSpan) * plotH;
  const hhmm = (ms: number) =>
    new Date(ms).toLocaleTimeString("en-AU", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone,
    });

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      className="w-full h-auto"
      role="img"
      aria-label={`${points.length} minute samples between ${hhmm(tMin)} and ${hhmm(tMax)}`}
    >
      {ticks(vMin, vMax, 3).map((tick) => (
        <g key={tick}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--viz-grid)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
          <text
            x={PAD.left - 8}
            y={y(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            fontSize={11}
            fill="var(--viz-muted)"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {tickLabel(tick)}
          </text>
        </g>
      ))}
      <path
        d={points
          .map((p, i) => `${i === 0 ? "M" : "L"}${x(new Date(p.at).getTime()).toFixed(1)},${y(p.value).toFixed(1)}`)
          .join(" ")}
        fill="none"
        stroke={colour}
        strokeWidth={1.5}
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      >
        <title>{`${points.length} samples, ${vMin}–${vMax}${unit ? ` ${unit}` : ""}`}</title>
      </path>
      <text x={PAD.left} y={height - 6} fontSize={11} fill="var(--viz-muted)">
        {hhmm(tMin)}
      </text>
      <text x={W - PAD.right} y={height - 6} textAnchor="end" fontSize={11} fill="var(--viz-muted)">
        {hhmm(tMax)}
      </text>
    </svg>
  );
}
