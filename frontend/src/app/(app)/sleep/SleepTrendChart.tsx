import { Crosshair, type CrosshairColumn } from "../Crosshair";

/**
 * The trend view's master chart: every night, and every overnight signal, on
 * one plot.
 *
 * **One scale, four units, and that is stated on the page.** Resting heart
 * rate, HRV, breathing rate and blood oxygen are measured in bpm, ms, breaths
 * per minute and percent - but each of them lives inside 0-100 in its own
 * unit, and sleep does too once an hour is worth ten. So they share the axis
 * rather than each getting a strip, and the ten-unit grid means one hour, ten
 * bpm, ten ms and ten points of oxygen all at once.
 *
 * This is the app's one exception to "never two y-axes", and it holds for the
 * reason the trends page's recovery panel holds: the series genuinely occupy
 * the same numeric range, so their crossings are real rather than an artefact
 * of scaling. The hours axis on the right is the same scale relabelled, not a
 * second one - a thermometer marked in both C and F, not two thermometers.
 *
 * **What it costs, honestly.** Blood oxygen moving 93 to 97 is four percent of
 * this axis, so its line is nearly flat here and its variation is not readable
 * off this chart. That is the trade for being able to see a short night, a
 * raised resting heart rate and a low oxygen minimum line up on the same
 * evening, which four separately-scaled strips could never show. The night
 * page keeps per-signal scales for when the shape of one signal is the
 * question.
 *
 * **Colour carries efficiency on the bars.** Height already says how long the
 * night was; a tall red bar is a long time in bed slept badly, which is a
 * different night from a tall green one and was an identical mark before.
 */

export type NightBar = {
  date: string;
  minutes: number;
  efficiency: number | null;
  hasHypnogram: boolean;
};

export type OverlaySeries = {
  label: string;
  unit: string;
  points: Array<{ date: string; value: number }>;
  colour: string;
};

//: Sized for a full content column. The ratio of `W` to the total height is
//: the rendered aspect ratio, and ~2.3:1 puts the chart at roughly two-thirds
//: of a laptop viewport with the table still reachable below it.
const W = 1200;
const PAD = { top: 18, right: 74, bottom: 0, left: 52 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = 470;
const AXIS_H = 26;

//: Ten units to the hour. The whole design rests on this: it is what brings
//: sleep duration into the same 0-100 space as the vitals, and what makes one
//: gridline mean an hour and ten bpm at the same time.
const UNITS_PER_HOUR = 10;

/** Efficiency onto the shared 1-5 score ramp. Cut points from `scoring.py`. */
function efficiencyFill(efficiency: number | null): string {
  if (efficiency === null) return "var(--viz-muted)";
  if (efficiency >= 90) return "var(--viz-score-5)";
  if (efficiency >= 85) return "var(--viz-score-4)";
  if (efficiency >= 80) return "var(--viz-score-3)";
  if (efficiency >= 75) return "var(--viz-score-2)";
  return "var(--viz-score-1)";
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

function hm(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h ? `${h}h ${m.toString().padStart(2, "0")}m` : `${m}m`;
}

/** Label every Nth day, where N keeps the axis to about ten readable ticks. */
function dateStep(days: number): number {
  return [1, 2, 3, 7, 14, 30].find((step) => days / step <= 12) ?? 60;
}

/**
 * Split a series wherever it stops being nightly.
 *
 * A week the watch was not worn comes back as two clusters of points, and
 * joining them draws a confident line across days nobody measured - the most
 * quietly dishonest thing a line chart can do, and the same rule `charts.tsx`
 * applies to its daily series.
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

export function SleepTrendChart({
  nights,
  start,
  end,
  targetMinutes,
  overlays = [],
}: {
  nights: NightBar[];
  /** The window, not the data: an unworn week should read as a gap. */
  start: string;
  end: string;
  targetMinutes: number;
  overlays?: OverlaySeries[];
}) {
  if (nights.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        No nights recorded in this window.
      </p>
    );
  }

  const x0 = dayNumber(start);
  const x1 = dayNumber(end);
  const span = x1 - x0 || 1;
  const height = PAD.top + PLOT_H + AXIS_H;

  // One slot per day in the *window*, so gaps are visible as gaps rather than
  // being closed up by drawing only the nights that exist.
  const slotWidth = PLOT_W / (span + 1);
  const barWidth = Math.max(2, Math.min(26, slotWidth - 3));
  const x = (iso: string) => PAD.left + (dayNumber(iso) - x0) * slotWidth + slotWidth / 2;

  const asUnits = (minutes: number) => (minutes / 60) * UNITS_PER_HOUR;
  // 100 unless something exceeds it - a ten-hour night, or a heart rate over
  // 100 - in which case the axis grows in whole hours so the grid stays round.
  const highest = Math.max(
    100,
    ...nights.map((night) => asUnits(night.minutes)),
    ...overlays.flatMap((series) => series.points.map((point) => point.value)),
  );
  const yMax = Math.ceil(highest / UNITS_PER_HOUR) * UNITS_PER_HOUR;
  const y = (units: number) => PAD.top + PLOT_H - (units / yMax) * PLOT_H;

  const gridlines: number[] = [];
  for (let units = 0; units <= yMax; units += UNITS_PER_HOUR) gridlines.push(units);

  const step = dateStep(span + 1);
  const dateTicks: string[] = [];
  for (let day = x0; day <= x1; day += step) {
    dateTicks.push(new Date(day * 86_400_000).toISOString().slice(0, 10));
  }

  const lookup = overlays.map((series) => new Map(series.points.map((p) => [p.date, p.value])));

  // Every night is a crosshair column. Positions are fractions of the viewBox
  // so they stay right at any rendered width.
  const columns: CrosshairColumn[] = nights.map((night) => ({
    at: x(night.date) / W,
    title: shortLabel(night.date),
    rows: [
      { label: "Asleep", value: hm(night.minutes), colour: efficiencyFill(night.efficiency) },
      {
        label: "vs target",
        value: `${night.minutes - targetMinutes >= 0 ? "+" : "−"}${hm(Math.abs(night.minutes - targetMinutes))}`,
      },
      { label: "Efficiency", value: night.efficiency === null ? "—" : `${night.efficiency}%` },
      ...overlays.map((series, index) => {
        const value = lookup[index]?.get(night.date);
        return {
          label: series.label,
          value: value === undefined ? "—" : `${Math.round(value)} ${series.unit}`,
          colour: series.colour,
        };
      }),
    ],
  }));

  return (
    <Crosshair columns={columns}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Sleep duration per night from ${start} to ${end}, coloured by efficiency, with resting heart rate, HRV, breathing rate and lowest blood oxygen on the same scale`}
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
            {/* Left in the shared unit the vitals are read in, right in hours
                for the bars. One scale, two labellings. */}
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
              {units / UNITS_PER_HOUR}h
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

        {nights.map((night) => (
          <rect
            key={night.date}
            x={x(night.date) - barWidth / 2}
            y={y(asUnits(night.minutes))}
            width={barWidth}
            height={Math.max(1, PAD.top + PLOT_H - y(asUnits(night.minutes)))}
            rx={2}
            fill={efficiencyFill(night.efficiency)}
          >
            <title>
              {`${shortLabel(night.date)}: ${hm(night.minutes)}${
                night.efficiency === null ? "" : `, ${night.efficiency}% efficiency`
              }`}
            </title>
          </rect>
        ))}

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(asUnits(targetMinutes))}
          y2={y(asUnits(targetMinutes))}
          stroke="var(--viz-axis)"
          strokeWidth={1.5}
          strokeDasharray="6 4"
          vectorEffect="non-scaling-stroke"
        />
        <text
          x={W - PAD.right + 8}
          y={y(asUnits(targetMinutes)) - 8}
          fontSize={11}
          fill="var(--viz-muted)"
        >
          target
        </text>

        {overlays.map((series, index) =>
          runs(series.points).map((run, runIndex) => {
            const d = run
              .map(
                (point, i) =>
                  `${i === 0 ? "M" : "L"}${x(point.date).toFixed(1)},${y(point.value).toFixed(1)}`,
              )
              .join(" ");
            return (
              <g key={`${series.label}-${runIndex}`}>
                {/* A surface-coloured halo under each line, so four traces
                    crossing each other over filled bars stay separable. The
                    alternative - fading the bars - would mute the efficiency
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
                {runIndex === runs(series.points).length - 1 && run.length > 0 && (
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
 * Four series in four different units on one axis is only honest if the units
 * are named beside the colours - and the efficiency ramp has to say what it
 * means too, since colour is carrying data here rather than identity.
 */
export function MasterLegend({ overlays }: { overlays: OverlaySeries[] }) {
  const steps = [
    { label: "<75%", fill: "var(--viz-score-1)" },
    { label: "75–79", fill: "var(--viz-score-2)" },
    { label: "80–84", fill: "var(--viz-score-3)" },
    { label: "85–89", fill: "var(--viz-score-4)" },
    { label: "90%+", fill: "var(--viz-score-5)" },
  ];
  return (
    <div className="mb-3 space-y-1.5 text-xs text-slate-500 dark:text-slate-400">
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
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
        <li>Bars are time asleep, coloured by efficiency:</li>
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
      </ul>
    </div>
  );
}
