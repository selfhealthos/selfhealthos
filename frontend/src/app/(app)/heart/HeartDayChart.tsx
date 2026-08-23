import { Crosshair, type CrosshairColumn } from "../Crosshair";

/**
 * One day of heart rate, over the zones it moved through.
 *
 * The point of this chart is not the line - it is where the line *sits*. A
 * trace between 55 and 160 bpm is unreadable as a number, and completely
 * readable as "two hours in fat burn and twenty minutes above it" once the
 * zones are drawn behind it. So the bands are the ground and the trace is the
 * figure, and the zone minutes are printed in the legend from the same payload
 * the boundaries came from, so the picture and the totals cannot disagree.
 *
 * **The boundaries are the device's own.** Fitbit derives them from an
 * estimated maximum that moves with age, and the fat burn floor moves with
 * resting heart rate too. Recomputing 220-age here would draw bands that
 * contradict the minute totals beside them, so a day with no stored
 * boundaries gets no bands and says so rather than being given invented ones.
 *
 * **Sleep is shaded too.** Without it the long low stretch at each end of the
 * day looks like a sensor that stopped, and the depth of the overnight trough
 * - which is the one part of this chart that is about recovery rather than
 * effort - has nothing to be read against.
 */

export type TracePoint = { at: string; value: number };

//: `ceiling` and `minutes` are optional as well as nullable because that is
//: how the generated API types express a field with a default - and every
//: check below has to treat "absent" and "null" the same way anyway.
export type ZoneBand = {
  key: string;
  label: string;
  floor: number;
  ceiling?: number | null;
  minutes?: number | null;
};

export type SleepWindow = { started_at: string; ended_at: string };

//: Its own coordinate space, near the rendered width, for the reason
//: `nightcharts.tsx` gives: a 720-wide viewBox stretched across a full content
//: column renders an 11px label at 24px.
const W = 1200;
const PAD = { top: 16, right: 56, bottom: 0, left: 52 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = 460;
const AXIS_H = 26;

const ZONE_FILL: Record<string, string> = {
  fat_burn: "var(--viz-zone-fat-burn)",
  cardio: "var(--viz-zone-cardio)",
  peak: "var(--viz-zone-peak)",
};

/** Gridlines every 20 bpm, on round numbers rather than at the day's extremes. */
const BPM_STEP = 20;

export function HeartDayChart({
  start,
  end,
  timeZone,
  points,
  zones,
  sleep = [],
  restingHr = null,
}: {
  /** Local midnight to local midnight, so a quiet day is still a whole day. */
  start: string;
  end: string;
  timeZone: string;
  points: TracePoint[];
  zones: ZoneBand[];
  sleep?: SleepWindow[];
  restingHr?: number | null;
}) {
  const t0 = new Date(start).getTime();
  const t1 = new Date(end).getTime();
  const span = t1 - t0 || 1;
  const height = PAD.top + PLOT_H + AXIS_H;

  const values = points.map((point) => point.value);
  // The axis has to hold the trace *and* every band, or a zone whose floor sits
  // above the day's highest beat would be clipped off the top and the chart
  // would quietly stop showing that the zone exists.
  const low = Math.min(40, ...values, ...zones.map((zone) => zone.floor));
  const high = Math.max(
    100,
    ...values,
    ...zones.map((zone) => zone.ceiling ?? zone.floor + BPM_STEP),
  );
  const yLow = Math.floor(low / BPM_STEP) * BPM_STEP;
  const yHigh = Math.ceil(high / BPM_STEP) * BPM_STEP;

  const x = (iso: string | number) =>
    PAD.left +
    Math.min(1, Math.max(0, ((typeof iso === "number" ? iso : new Date(iso).getTime()) - t0) / span)) *
      PLOT_W;
  const y = (bpm: number) =>
    PAD.top + PLOT_H - ((bpm - yLow) / (yHigh - yLow || 1)) * PLOT_H;

  const hhmm = (ms: number) =>
    new Date(ms).toLocaleTimeString("en-AU", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone,
    });

  // On the hour in the wearer's own zone. Every two hours over a full day, so
  // twelve labels rather than twenty-four overlapping ones.
  const hours: number[] = [];
  const first = new Date(t0);
  first.setMinutes(60, 0, 0);
  for (let t = first.getTime(); t <= t1; t += 3_600_000) hours.push(t);
  const labelEvery = hours.length > 14 ? 2 : 1;

  const gridlines: number[] = [];
  for (let bpm = yLow; bpm <= yHigh; bpm += BPM_STEP) gridlines.push(bpm);

  // Split the trace wherever the watch stopped reporting. Joining across an
  // hour off the wrist draws a confident straight line through a gap, which is
  // the same lie the daily charts refuse to tell.
  const runs: TracePoint[][] = [];
  let run: TracePoint[] = [];
  points.forEach((point, index) => {
    const previous = points[index - 1];
    if (
      previous &&
      new Date(point.at).getTime() - new Date(previous.at).getTime() > 10 * 60_000
    ) {
      runs.push(run);
      run = [];
    }
    run.push(point);
  });
  if (run.length) runs.push(run);

  // A crosshair column every five minutes, matching the night stack: every
  // minute would be ~1,440 columns of tooltip data for a resolution no pointer
  // can hit.
  const byMinute = new Map(points.map((point) => [new Date(point.at).getTime(), point.value]));
  const columns: CrosshairColumn[] = [];
  for (let t = t0; t <= t1; t += 5 * 60_000) {
    let found: number | undefined;
    for (let offset = 0; offset < 5 && found === undefined; offset += 1) {
      found = byMinute.get(t + offset * 60_000);
    }
    const zone = found === undefined ? null : zoneAt(zones, found);
    columns.push({
      at: x(t) / W,
      title: hhmm(t),
      rows: [
        { label: "Heart rate", value: found === undefined ? "—" : `${Math.round(found)} bpm` },
        { label: "Zone", value: zone ? zone.label : found === undefined ? "—" : "Below fat burn" },
      ],
    });
  }

  if (points.length === 0 && zones.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        Nothing recorded on this day.
      </p>
    );
  }

  return (
    <Crosshair columns={columns}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Heart rate through the day from ${hhmm(t0)} to ${hhmm(t1)}, with the fat burn, cardio and peak zones shaded behind it`}
      >
        {/* Sleep first, furthest back: it is the widest region on the chart and
            anything drawn under the zones would tint them. */}
        {sleep.map((window) => (
          <rect
            key={window.started_at}
            x={x(window.started_at)}
            y={PAD.top}
            width={Math.max(1, x(window.ended_at) - x(window.started_at))}
            height={PLOT_H}
            fill="var(--viz-sleep-band)"
          >
            <title>{`Asleep ${hhmm(new Date(window.started_at).getTime())}–${hhmm(new Date(window.ended_at).getTime())}`}</title>
          </rect>
        ))}

        {zones.map((zone) => {
          const top = zone.ceiling ?? yHigh;
          return (
            <g key={zone.key}>
              <rect
                x={PAD.left}
                y={y(Math.min(top, yHigh))}
                width={PLOT_W}
                height={Math.max(1, y(zone.floor) - y(Math.min(top, yHigh)))}
                fill={ZONE_FILL[zone.key] ?? "var(--viz-zone-fat-burn)"}
              >
                <title>
                  {`${zone.label}: ${zone.floor}${zone.ceiling ? `–${zone.ceiling}` : "+"} bpm${
                    zone.minutes == null ? "" : `, ${Math.round(zone.minutes)} min`
                  }`}
                </title>
              </rect>
              {/* The floor labelled on the axis side, because the band's
                  meaning is entirely in where it starts. */}
              <text
                x={W - PAD.right + 6}
                y={y(zone.floor) - 4}
                fontSize={11}
                fill="var(--viz-muted)"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {zone.label}
              </text>
            </g>
          );
        })}

        {gridlines.map((bpm) => (
          <g key={bpm}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(bpm)}
              y2={y(bpm)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={PAD.left - 8}
              y={y(bpm)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {bpm}
            </text>
          </g>
        ))}

        {hours.map((t, index) =>
          index % labelEvery === 0 ? (
            <line
              key={t}
              x1={x(t)}
              x2={x(t)}
              y1={PAD.top}
              y2={PAD.top + PLOT_H}
              stroke="var(--viz-grid)"
              strokeWidth={1}
              strokeOpacity={0.7}
              vectorEffect="non-scaling-stroke"
            />
          ) : null,
        )}

        {restingHr !== null && restingHr >= yLow && (
          <>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(restingHr)}
              y2={y(restingHr)}
              stroke="var(--viz-axis)"
              strokeWidth={1.5}
              strokeDasharray="6 4"
              vectorEffect="non-scaling-stroke"
            />
            <text x={PAD.left + 6} y={y(restingHr) - 6} fontSize={11} fill="var(--viz-muted)">
              resting {Math.round(restingHr)}
            </text>
          </>
        )}

        {runs.map((segment) => (
          <path
            key={segment[0]?.at ?? "empty"}
            d={segment
              .map(
                (point, index) =>
                  `${index === 0 ? "M" : "L"}${x(point.at).toFixed(1)},${y(point.value).toFixed(1)}`,
              )
              .join(" ")}
            fill="none"
            stroke="var(--viz-8)"
            strokeWidth={1.4}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={PAD.top + PLOT_H}
          y2={PAD.top + PLOT_H}
          stroke="var(--viz-axis)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
        {hours.map((t, index) =>
          index % labelEvery === 0 ? (
            <text
              key={t}
              x={x(t)}
              y={height - 8}
              textAnchor="middle"
              fontSize={11}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {hhmm(t)}
            </text>
          ) : null,
        )}
      </svg>
    </Crosshair>
  );
}

/** The zone a reading falls in, or null for anything below fat burn. */
function zoneAt(zones: ZoneBand[], bpm: number): ZoneBand | null {
  let found: ZoneBand | null = null;
  for (const zone of zones) {
    if (bpm >= zone.floor && (zone.ceiling == null || bpm < zone.ceiling)) found = zone;
  }
  return found;
}

/**
 * The zone key, carrying the minute totals.
 *
 * The numbers live in the legend rather than on the bands because a band is a
 * region and a total is a fact about the whole day - printing "150 min" inside
 * a stripe reads as a claim about that stripe's width, which is time of day.
 */
export function ZoneLegend({ zones, asleep }: { zones: ZoneBand[]; asleep: boolean }) {
  if (zones.length === 0) {
    return (
      <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">
        No zone boundaries stored for this day, so the bands are not drawn. Days synced from now on
        carry them; re-run the backfill to fill in older ones.
      </p>
    );
  }
  return (
    <ul className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
      {zones.map((zone) => (
        <li key={zone.key} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2.5 rounded-sm border border-slate-200 dark:border-slate-700"
            style={{ backgroundColor: ZONE_FILL[zone.key] }}
          />
          {zone.label}
          <span className="text-slate-400 dark:text-slate-600">
            {zone.floor}
            {zone.ceiling ? `–${zone.ceiling}` : "+"}
          </span>
          {zone.minutes != null && <span className="tabular-nums">{Math.round(zone.minutes)}m</span>}
        </li>
      ))}
      {asleep && (
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2.5 rounded-sm border border-slate-200 dark:border-slate-700"
            style={{ backgroundColor: "var(--viz-sleep-band)" }}
          />
          Asleep
        </li>
      )}
    </ul>
  );
}
