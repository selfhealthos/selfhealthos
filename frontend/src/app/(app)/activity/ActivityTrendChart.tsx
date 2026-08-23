import { Crosshair, type CrosshairColumn } from "../Crosshair";

/**
 * The window view's master chart: every day's steps, and how hard they were.
 *
 * **Height is volume, colour is intensity.** That split is the whole reason
 * this chart exists. A day of 15,000 steps with eight active minutes and a day
 * of 15,000 with fifty-five are the same distance and not remotely the same
 * day, and on the line chart this replaces they were an identical mark. The
 * colour ramp is `scoring.ACTIVE_MINUTES` - the WHO's 150-300 minutes a week -
 * so a bar and its row in the table below cannot disagree.
 *
 * **One scale, three units, and that is stated on the page.** Steps ride the
 * shared axis at 200 to the unit, which puts the 10,000 goal on 50 and 20,000
 * on 100. Active minutes, vigorous minutes and resting heart rate are already
 * inside 0-100 in their own units, so they need no conversion at all. One
 * gridline is therefore 2,000 steps, ten minutes and ten bpm at once.
 *
 * The axis grows a gridline at a time past 100 when anything exceeds it, so
 * the goal line is only mid-plot on a window whose busiest day stayed under
 * 20,000 steps and whose hardest stayed under a hundred active minutes. A
 * single 147-minute day pushes the top to 150 and the goal down to a third -
 * which is the correct trade: clamping the axis instead would clip that day
 * off the top, and a chart that hides its own outlier is worse than one whose
 * reference line moves.
 *
 * This is the same exception to "never two y-axes" the sleep page takes, and
 * it holds for the same reason: the series genuinely occupy one numeric range,
 * so their crossings are real rather than an artefact of scaling. The steps
 * axis on the right is that scale relabelled, not a second one.
 *
 * **What it costs, honestly.** Vigorous minutes average under three a day
 * here, so that line hugs the floor - and that *is* the finding, not a defect
 * of the chart. The gap between it and the active-minutes line is the picture
 * of intensity this page is for. Resting heart rate, at 58-85, spends the
 * whole window in the upper half and moves within a few units of it; read it
 * for direction over weeks, not for daily change.
 *
 * **The trailing mean is drawn over the bars** because daily steps here swing
 * from zero to twenty thousand, and a bar forest that noisy has no readable
 * trend in it. It is literally an average of the bar heights, in the same
 * unit, which is why it is drawn in ink rather than given a series colour: it
 * is not a fourth signal, it is these bars with the noise taken out.
 */

export type StepBar = {
  date: string;
  steps: number;
  activeMinutes: number | null;
  band: number | null;
};

export type OverlaySeries = {
  label: string;
  unit: string;
  points: Array<{ date: string; value: number }>;
  colour: string;
};

//: Sized to match the sleep page's master chart, so the two read as the same
//: instrument at the same scale when flipped between.
const W = 1200;
const PAD = { top: 18, right: 78, bottom: 0, left: 52 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = 470;
const AXIS_H = 26;

//: Steps to one unit of the shared axis. 200 is not arbitrary: it is the
//: number that lands the 10,000 goal on 50 and 20,000 on 100, so the reference
//: line sits mid-plot and the axis tops out at a round figure the person
//: recognises.
const STEPS_PER_UNIT = 200;

//: One gridline. Ten units is 2,000 steps, ten minutes and ten bpm.
const UNITS_PER_LINE = 10;

/** Intensity onto the shared 1-5 score ramp. Bands come from the API, which
 *  scores them with `scoring.ACTIVE_MINUTES` - the same thresholds the table
 *  below colours against. */
function intensityFill(band: number | null): string {
  return band === null ? "var(--viz-muted)" : `var(--viz-score-${band})`;
}

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

/** Label every Nth day, where N keeps the axis to about ten readable ticks. */
function dateStep(days: number): number {
  return [1, 2, 3, 7, 14, 30].find((step) => days / step <= 12) ?? 60;
}

/**
 * Split a series wherever it stops being daily.
 *
 * A third of the last year has no data at all, so this is not a hypothetical:
 * joining across an unworn fortnight draws a confident line through days
 * nobody measured, which is the most quietly dishonest thing a line chart can
 * do. Same rule as `charts.tsx` and the sleep page.
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
  return out.filter((run) => run.length > 0);
}

export function ActivityTrendChart({
  bars,
  trailing,
  overlays = [],
  start,
  end,
  goal,
}: {
  bars: StepBar[];
  /** Seven-day trailing mean of steps, already sparse where the week was too
   *  thin to average. */
  trailing: Array<{ date: string; value: number }>;
  overlays?: OverlaySeries[];
  /** The window, not the data: an unworn week should read as a gap. */
  start: string;
  end: string;
  goal: number;
}) {
  if (bars.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        No days with a step count in this window.
      </p>
    );
  }

  const x0 = dayNumber(start);
  const x1 = dayNumber(end);
  const span = x1 - x0 || 1;
  const height = PAD.top + PLOT_H + AXIS_H;

  // One slot per day in the *window*, so gaps are visible as gaps rather than
  // being closed up by drawing only the days that exist.
  const slotWidth = PLOT_W / (span + 1);
  const barWidth = Math.max(2, Math.min(26, slotWidth - 3));
  const x = (iso: string) => PAD.left + (dayNumber(iso) - x0) * slotWidth + slotWidth / 2;

  const asUnits = (steps: number) => steps / STEPS_PER_UNIT;
  // 100 unless something exceeds it - a 21,000-step day, or a resting heart
  // rate over 100 - in which case the axis grows a gridline at a time so the
  // grid stays round.
  const highest = Math.max(
    100,
    ...bars.map((bar) => asUnits(bar.steps)),
    ...overlays.flatMap((series) => series.points.map((point) => point.value)),
  );
  const yMax = Math.ceil(highest / UNITS_PER_LINE) * UNITS_PER_LINE;
  const y = (units: number) => PAD.top + PLOT_H - (units / yMax) * PLOT_H;

  const gridlines: number[] = [];
  for (let units = 0; units <= yMax; units += UNITS_PER_LINE) gridlines.push(units);

  const step = dateStep(span + 1);
  const dateTicks: string[] = [];
  for (let day = x0; day <= x1; day += step) {
    dateTicks.push(new Date(day * 86_400_000).toISOString().slice(0, 10));
  }

  const lookup = overlays.map((series) => new Map(series.points.map((p) => [p.date, p.value])));
  const trailingAt = new Map(trailing.map((point) => [point.date, point.value]));

  // Every day with steps is a crosshair column. Positions are fractions of the
  // viewBox so they stay right at any rendered width.
  const columns: CrosshairColumn[] = bars.map((bar) => {
    const mean = trailingAt.get(bar.date);
    return {
      at: x(bar.date) / W,
      title: shortLabel(bar.date),
      rows: [
        {
          label: "Steps",
          value: Math.round(bar.steps).toLocaleString(),
          colour: intensityFill(bar.band),
        },
        {
          label: "vs goal",
          value: `${bar.steps - goal >= 0 ? "+" : "−"}${Math.abs(
            Math.round(bar.steps - goal),
          ).toLocaleString()}`,
        },
        { label: "7-day mean", value: mean === undefined ? "—" : Math.round(mean).toLocaleString() },
        ...overlays.map((series, index) => {
          const value = lookup[index]?.get(bar.date);
          return {
            label: series.label,
            value: value === undefined ? "—" : `${Math.round(value)} ${series.unit}`,
            colour: series.colour,
          };
        }),
      ],
    };
  });

  const trailingRuns = runs(trailing);

  return (
    <Crosshair columns={columns}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Steps per day from ${start} to ${end}, coloured by moderate-to-vigorous minutes, with a seven-day trailing mean, active minutes, vigorous minutes and resting heart rate on the same scale`}
      >
        {gridlines.map((units) => (
          <g key={units}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(units)}
              y2={y(units)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            {/* Left in the shared unit the overlays are read in, right in
                steps for the bars. One scale, two labellings. */}
            <text
              x={PAD.left - 8}
              y={y(units)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {units}
            </text>
            <text
              x={W - PAD.right + 8}
              y={y(units)}
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {(units * STEPS_PER_UNIT) / 1000}k
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

        {bars.map((bar) => (
          <rect
            key={bar.date}
            x={x(bar.date) - barWidth / 2}
            y={y(asUnits(bar.steps))}
            width={barWidth}
            height={Math.max(1, PAD.top + PLOT_H - y(asUnits(bar.steps)))}
            rx={2}
            fill={intensityFill(bar.band)}
          >
            <title>
              {`${shortLabel(bar.date)}: ${Math.round(bar.steps).toLocaleString()} steps${
                bar.activeMinutes === null
                  ? " (no intensity recorded)"
                  : `, ${Math.round(bar.activeMinutes)} active minutes`
              }`}
            </title>
          </rect>
        ))}

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(asUnits(goal))}
          y2={y(asUnits(goal))}
          stroke="var(--viz-axis)"
          strokeWidth={1.5}
          strokeDasharray="6 4"
          vectorEffect="non-scaling-stroke"
        />
        <text x={W - PAD.right + 8} y={y(asUnits(goal)) - 8} fontSize={11} fill="var(--viz-muted)">
          goal
        </text>

        {/* The trailing mean, in ink rather than a series colour: it is these
            bars with the noise removed, not a fourth signal. */}
        {trailingRuns.map((run, runIndex) => {
          const d = run
            .map(
              (point, i) =>
                `${i === 0 ? "M" : "L"}${x(point.date).toFixed(1)},${y(asUnits(point.value)).toFixed(1)}`,
            )
            .join(" ");
          return (
            <g key={`trailing-${runIndex}`}>
              <path
                d={d}
                fill="none"
                stroke="var(--viz-surface)"
                strokeWidth={6}
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeOpacity={0.85}
                vectorEffect="non-scaling-stroke"
              />
              <path
                d={d}
                fill="none"
                stroke="var(--viz-muted)"
                strokeWidth={2.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            </g>
          );
        })}

        {overlays.map((series, index) =>
          runs(series.points).map((run, runIndex, all) => {
            const d = run
              .map(
                (point, i) =>
                  `${i === 0 ? "M" : "L"}${x(point.date).toFixed(1)},${y(point.value).toFixed(1)}`,
              )
              .join(" ");
            return (
              <g key={`${series.label}-${runIndex}`}>
                {/* A surface-coloured halo under each line, so three traces
                    crossing each other over filled bars stay separable. The
                    alternative - fading the bars - would mute the intensity
                    colour, which is data. */}
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
                  stroke={series.colour}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
                {/* The last point labelled with its own unit, since the axis
                    cannot say which unit any given line is in. */}
                {runIndex === all.length - 1 && run.length > 0 && (
                  <text
                    x={Math.min(W - PAD.right + 6, x(run[run.length - 1]!.date) + 8)}
                    y={y(run[run.length - 1]!.value) - 6}
                    fontSize={11}
                    fill={series.colour}
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {Math.round(run[run.length - 1]!.value)}
                    {series.unit}
                  </text>
                )}
              </g>
            );
          }),
        )}

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
 * Three series in three units on one axis is only honest if the units are
 * named beside the colours - and the intensity ramp has to say what it means
 * too, since colour is carrying data here rather than identity. The cut points
 * are `scoring.ACTIVE_MINUTES`, printed in minutes so the ramp can be read
 * without opening the table.
 */
export function MasterLegend({ overlays }: { overlays: OverlaySeries[] }) {
  const steps = [
    // Where the five bands actually fall on `scoring.ACTIVE_MINUTES`, not
    // even fifths of the WHO range: the curve is steepest below ten minutes,
    // so the bottom bands are narrow and the top one opens at twenty.
    { label: "<5", fill: "var(--viz-score-1)" },
    { label: "5–9", fill: "var(--viz-score-2)" },
    { label: "10–14", fill: "var(--viz-score-3)" },
    { label: "15–19", fill: "var(--viz-score-4)" },
    { label: "20+ min", fill: "var(--viz-score-5)" },
  ];
  return (
    <div className="mb-3 space-y-1.5 text-xs text-slate-500 dark:text-slate-400">
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="h-0.5 w-4 rounded-full"
            style={{ backgroundColor: "var(--viz-muted)" }}
          />
          Steps, 7-day mean
        </li>
        {overlays.map((series) => (
          <li key={series.label} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="h-0.5 w-4 rounded-full"
              style={{ backgroundColor: series.colour }}
            />
            {series.label} <span className="text-slate-400 dark:text-slate-600">{series.unit}</span>
          </li>
        ))}
      </ul>
      <ul className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <li>Bars are steps, coloured by moderate-to-vigorous minutes:</li>
        {steps.map((step) => (
          <li key={step.label} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="size-2.5 rounded-sm"
              style={{ backgroundColor: step.fill }}
            />
            {step.label}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2.5 rounded-sm"
            style={{ backgroundColor: "var(--viz-muted)" }}
          />
          not recorded
        </li>
      </ul>
    </div>
  );
}
