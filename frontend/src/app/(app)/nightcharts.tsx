import { ticks, tickLabel } from "./charts";
import { Crosshair, type CrosshairColumn } from "./Crosshair";

/**
 * One night, on one time axis.
 *
 * These are separate from `charts.tsx` because their x axis is a *clock inside
 * a single night* rather than a calendar, and because everything here shares
 * one axis by construction: the hypnogram, the heart rate and the blood oxygen
 * are drawn into one SVG with one `x()`, so a spike and a dip that line up
 * vertically genuinely happened at the same moment. Three separate charts in
 * three cards cannot promise that - they would each scale to their own extent,
 * and reading across them would be a guess.
 *
 * The design follows how a sleep study is read: stages at the top as a
 * hypnogram, the physiology stacked beneath it, and any oxygen dip drawn as a
 * vertical band running through every panel - which is the mark that answers
 * "did the heart rate move when the oxygen fell?" without the reader measuring
 * anything.
 */

export type Segment = {
  level: string;
  started_at: string;
  ended_at: string;
  seconds: number;
  is_short: boolean;
};

export type NightPoint = { at: string; value: number };

export type Panel = {
  label: string;
  unit: string;
  points: NightPoint[];
  colour: string;
  /** Clinical normal range, shaded behind the trace. */
  normalBand?: { from: number; to: number };
  /** A single threshold line - 90% for oxygen. */
  reference?: { value: number; label: string };
  /**
   * Gridline spacing in the panel's own unit - 10 bpm for a heart rate.
   *
   * Ticks on round numbers rather than at whatever extremes the night happened
   * to reach: "62 to 71" is a scale nobody can read a value off, and it also
   * changes from night to night, so two nights cannot be compared by eye.
   */
  step?: number;
};

/** Moments worth marking across every panel, e.g. oxygen dips. */
export type Mark = { from: string; to: string; label: string };

//: Lanes top to bottom, the order a sleep study prints them: awake at the top,
//: deepest at the bottom, so the trace falls as sleep deepens.
const LANES = [
  { level: "wake", label: "Awake", color: "var(--viz-stage-awake)" },
  { level: "rem", label: "REM", color: "var(--viz-stage-rem)" },
  { level: "light", label: "Light", color: "var(--viz-stage-light)" },
  { level: "deep", label: "Deep", color: "var(--viz-stage-deep)" },
] as const;

//: Levels from devices with no stage tracking, and Fitbit's older "classic"
//: logs. Mapped onto a lane for drawing only - the label keeps saying what was
//: actually recorded, because "asleep" is not a claim that it was light sleep.
const FALLBACK_LANE: Record<string, string> = {
  asleep: "light",
  restless: "light",
  awake: "wake",
  unknown: "light",
};

//: Its own coordinate space rather than the shared one in `charts.tsx`, which
//: is tuned for a chart in a two-up grid. Scaling a 720-wide viewBox across a
//: full content column magnifies everything in it - an 11px label renders at
//: 24px - so a master chart needs a viewBox near its rendered width. These
//: numbers are also the layout: `h-auto` derives the height from their ratio.
const W = 1200;
const PAD = { top: 16, right: 60, bottom: 0, left: 58 };
const PLOT_W = W - PAD.left - PAD.right;
const LANE_H = 26;
const HYPNO_H = LANES.length * LANE_H + 10;
const PANEL_H = 120;
const AXIS_H = 26;

function laneIndex(level: string): number {
  const key = LANES.findIndex((lane) => lane.level === level);
  if (key >= 0) return key;
  return LANES.findIndex((lane) => lane.level === (FALLBACK_LANE[level] ?? "light"));
}

function laneColour(level: string): string {
  const lane = LANES[laneIndex(level)];
  return lane ? lane.color : "var(--viz-stage-awake)";
}

//: Stage names as a person reads them, including the unstaged levels that have
//: no lane of their own.
const LABELS: Record<string, string> = {
  deep: "Deep",
  light: "Light",
  rem: "REM",
  wake: "Awake",
  asleep: "Asleep (unstaged)",
  restless: "Restless",
  awake: "Awake (unstaged)",
  unknown: "Unknown",
};

/** Gridlines at round values in the panel's unit, or `ticks`' own choice. */
function panelTicks(low: number, high: number, step?: number): number[] {
  if (!step) return ticks(low, high, 2);
  const out: number[] = [];
  for (let value = Math.ceil(low / step) * step; value <= high; value += step) {
    out.push(Math.round(value * 10) / 10);
  }
  return out;
}

/**
 * The reading closest to `t`, or an em dash.
 *
 * Nearest rather than interpolated: these are measurements, and a value
 * invented between two of them is a number the watch never recorded. Anything
 * further than two minutes away is a gap, not a reading.
 */
function nearest(points: NightPoint[], t: number): string {
  let best: NightPoint | null = null;
  let bestGap = Infinity;
  for (const point of points) {
    const gap = Math.abs(new Date(point.at).getTime() - t);
    if (gap < bestGap) {
      bestGap = gap;
      best = point;
    }
  }
  return best && bestGap <= 120_000 ? `${Math.round(best.value)}` : "—";
}

/**
 * The hypnogram, the stacked physiology, and a shared clock.
 *
 * `start` and `end` bound the axis explicitly rather than being taken from the
 * data: the heart rate may stop ten minutes before the alarm, and letting the
 * series define the window would silently trim the night to whatever the watch
 * happened to record.
 */
export function NightStack({
  start,
  end,
  timeZone,
  segments,
  panels,
  marks = [],
}: {
  start: string;
  end: string;
  timeZone: string;
  segments: Segment[];
  panels: Panel[];
  marks?: Mark[];
}) {
  const t0 = new Date(start).getTime();
  const t1 = new Date(end).getTime();
  const span = t1 - t0 || 1;
  const height = HYPNO_H + panels.length * PANEL_H + AXIS_H + PAD.top;

  const x = (iso: string) =>
    PAD.left + Math.min(1, Math.max(0, (new Date(iso).getTime() - t0) / span)) * PLOT_W;
  const hhmm = (ms: number) =>
    new Date(ms).toLocaleTimeString("en-AU", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone,
    });

  // An hourly grid, on the hour in the wearer's own zone rather than every
  // 60 minutes from lights-out - "03:00" is a time a person can reason about,
  // "02:47" is an artefact of when they went to bed.
  const hours: number[] = [];
  const first = new Date(t0);
  first.setMinutes(60, 0, 0);
  for (let t = first.getTime(); t <= t1; t += 3_600_000) hours.push(t);
  const step = hours.length > 10 ? 2 : 1;

  const main = segments.filter((segment) => !segment.is_short);
  const short = segments.filter((segment) => segment.is_short);

  // A crosshair column every five minutes. Every minute would be ~500 columns
  // of tooltip data in the payload for a resolution no pointer can hit, and
  // five minutes is finer than the eye can distinguish at this width anyway.
  const columns: CrosshairColumn[] = [];
  for (let t = t0; t <= t1; t += 5 * 60_000) {
    const at = new Date(t).toISOString();
    const stage = main.find(
      (segment) => new Date(segment.started_at).getTime() <= t && new Date(segment.ended_at).getTime() > t,
    );
    columns.push({
      at: x(at) / W,
      title: hhmm(t),
      rows: [
        { label: "Stage", value: stage ? LABELS[stage.level] ?? stage.level : "—" },
        ...panels.map((panel) => ({
          label: panel.label,
          value: nearest(panel.points, t),
          colour: panel.colour,
        })),
      ],
    });
  }

  return (
    <Crosshair columns={columns}>
    <svg
      viewBox={`0 0 ${W} ${height}`}
      className="w-full h-auto"
      role="img"
      aria-label={`Sleep stages and overnight physiology from ${hhmm(t0)} to ${hhmm(t1)}`}
    >
      {/* Marks first, behind everything, spanning the full height: they are
          the "look here" layer, and a band drawn over the traces would hide
          the very thing it is pointing at. */}
      {marks.map((mark) => (
        <rect
          key={mark.from}
          x={x(mark.from)}
          y={PAD.top}
          // A one-minute dip is a third of a pixel wide at this scale, which is
          // invisible. 2px is the floor for a mark that has to be findable.
          width={Math.max(2, x(mark.to) - x(mark.from))}
          height={height - PAD.top - AXIS_H}
          fill="var(--viz-event-band)"
        >
          <title>{mark.label}</title>
        </rect>
      ))}

      {hours
        .filter((_, index) => index % step === 0)
        .map((hour) => (
          <line
            key={hour}
            x1={x(new Date(hour).toISOString())}
            x2={x(new Date(hour).toISOString())}
            y1={PAD.top}
            y2={height - AXIS_H}
            stroke="var(--viz-grid)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ))}

      {/* -- the hypnogram ------------------------------------------------ */}
      {LANES.map((lane, index) => (
        <text
          key={lane.level}
          x={PAD.left - 8}
          y={PAD.top + index * LANE_H + LANE_H / 2}
          textAnchor="end"
          dominantBaseline="middle"
          fontSize={10}
          fill="var(--viz-muted)"
        >
          {lane.label}
        </text>
      ))}

      {main.map((segment) => {
        const left = x(segment.started_at);
        const width = Math.max(1, x(segment.ended_at) - left);
        return (
          <rect
            key={`${segment.started_at}-${segment.level}`}
            x={left}
            y={PAD.top + laneIndex(segment.level) * LANE_H + 3}
            width={width}
            height={LANE_H - 6}
            rx={2}
            fill={laneColour(segment.level)}
          >
            <title>
              {`${segment.level} — ${hhmm(new Date(segment.started_at).getTime())} for ${Math.round(
                segment.seconds / 60,
              )} min`}
            </title>
          </rect>
        );
      })}

      {/* The stepped trace over the blocks. Blocks answer "how much of what",
          the line answers "where did the night go" - it is the shape a sleep
          study is read by, and it makes a descent into deep sleep in the first
          cycle visible as a descent rather than as two adjacent rectangles. */}
      {main.length > 1 && (
        <path
          d={main
            .map((segment, index) => {
              const laneY = PAD.top + laneIndex(segment.level) * LANE_H + LANE_H / 2;
              const left = x(segment.started_at);
              const right = x(segment.ended_at);
              // `L` back to the same y at the segment's start draws the vertical
              // riser between stages; the first point only moves there.
              return `${index === 0 ? "M" : "L"}${left.toFixed(1)},${laneY.toFixed(1)} L${right.toFixed(1)},${laneY.toFixed(1)}`;
            })
            .join(" ")}
          fill="none"
          stroke="var(--viz-muted)"
          strokeWidth={1}
          strokeOpacity={0.65}
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      )}

      {/* Short wakes as ticks on the awake lane. Fitbit reports these apart
          from the main trace because they are stirrings rather than periods,
          and drawing them as full blocks would fragment the night visually in
          a way the scoring itself does not. */}
      {short.map((segment) => (
        <rect
          key={`short-${segment.started_at}`}
          x={x(segment.started_at)}
          y={PAD.top + 1}
          width={Math.max(1, x(segment.ended_at) - x(segment.started_at))}
          height={5}
          fill="var(--viz-stage-awake)"
        >
          <title>
            {`brief stir — ${hhmm(new Date(segment.started_at).getTime())}, ${Math.round(
              segment.seconds / 60,
            )} min`}
          </title>
        </rect>
      ))}

      {/* -- the stacked panels ------------------------------------------- */}
      {panels.map((panel, index) => {
        const top = PAD.top + HYPNO_H + index * PANEL_H;
        const plot = PANEL_H - 18;
        const values = panel.points.map((point) => point.value);
        const candidates = [
          ...values,
          ...(panel.normalBand ? [panel.normalBand.from, panel.normalBand.to] : []),
          ...(panel.reference ? [panel.reference.value] : []),
        ];
        const low = candidates.length ? Math.min(...candidates) : 0;
        const high = candidates.length ? Math.max(...candidates) : 1;
        const pad = (high - low || 1) * 0.1;
        const yMin = low - pad;
        const yMax = high + pad;
        const y = (value: number) =>
          top + plot - ((value - yMin) / (yMax - yMin || 1)) * plot;

        return (
          <g key={panel.label}>
            {panel.normalBand && (
              <rect
                x={PAD.left}
                y={y(panel.normalBand.to)}
                width={PLOT_W}
                height={Math.abs(y(panel.normalBand.from) - y(panel.normalBand.to))}
                fill="var(--viz-normal-band)"
              />
            )}

            {panelTicks(yMin, yMax, panel.step).map((tick) => (
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
                  fontSize={10}
                  fill="var(--viz-muted)"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {tickLabel(tick)}
                </text>
              </g>
            ))}

            {panel.reference && (
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(panel.reference.value)}
                y2={y(panel.reference.value)}
                stroke="var(--viz-critical)"
                strokeWidth={1}
                strokeDasharray="4 3"
                vectorEffect="non-scaling-stroke"
              />
            )}

            {panel.points.length > 0 ? (
              <path
                d={panel.points
                  .map(
                    (point, i) =>
                      `${i === 0 ? "M" : "L"}${x(point.at).toFixed(1)},${y(point.value).toFixed(1)}`,
                  )
                  .join(" ")}
                fill="none"
                stroke={panel.colour}
                strokeWidth={1.5}
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            ) : (
              <text
                x={PAD.left + PLOT_W / 2}
                y={top + plot / 2}
                textAnchor="middle"
                fontSize={11}
                fill="var(--viz-muted)"
              >
                Nothing recorded for {panel.label.toLowerCase()} this night
              </text>
            )}

            <text x={PAD.left} y={top - 4} fontSize={11} fill="var(--viz-muted)">
              {panel.label}
              {panel.unit ? ` (${panel.unit})` : ""}
            </text>
          </g>
        );
      })}

      {/* -- the shared clock --------------------------------------------- */}
      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={height - AXIS_H}
        y2={height - AXIS_H}
        stroke="var(--viz-axis)"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
      {hours
        .filter((_, index) => index % step === 0)
        .map((hour) => (
          <text
            key={hour}
            x={x(new Date(hour).toISOString())}
            y={height - 6}
            textAnchor="middle"
            fontSize={10}
            fill="var(--viz-muted)"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {hhmm(hour)}
          </text>
        ))}
    </svg>
    </Crosshair>
  );
}

/** The stage legend, matching the lanes above. */
export function StageLegend() {
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
      {LANES.map((lane) => (
        <li
          key={lane.level}
          className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400"
        >
          <span aria-hidden className="size-2.5 rounded-sm" style={{ backgroundColor: lane.color }} />
          {lane.label}
        </li>
      ))}
    </ul>
  );
}
