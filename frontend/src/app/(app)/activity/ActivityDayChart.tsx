import { Crosshair, type CrosshairColumn } from "../Crosshair";

/**
 * One day of steps: the climb, and the hours it was made of.
 *
 * A day's activity is two questions and they want two marks. *Did I get
 * there?* is a cumulative curve against a flat goal - the only shape in which
 * "on track at 3pm" is a thing you can see rather than calculate. *When did it
 * happen?* is hourly bars, because a day of one long walk and a day of steady
 * pottering can end on the same number and are not the same day.
 *
 * **Minutes for the line, hours for the bars.** Per-minute steps drawn as bars
 * are a 1,440-tooth comb that resolves to a grey smear; per-hour steps drawn
 * as a curve lose the thing the curve is for, which is the exact moment the
 * line was crossed. So each mark gets the resolution it can actually carry,
 * out of one query.
 *
 * **Sleep is shaded** for the same reason it is on the heart day chart:
 * without it, eight hours of a perfectly flat cumulative line looks like a
 * sensor that stopped rather than a person who was asleep.
 */

export type ClimbPoint = { at: string; value: number };
export type HourBar = { hour: number; steps: number };
export type SleepWindow = { started_at: string; ended_at: string };

//: Its own coordinate space, near the rendered width, matching the heart day
//: chart - a 720-wide viewBox stretched across a full content column renders
//: an 11px label at 24px.
const W = 1200;
const PAD = { top: 16, right: 62, bottom: 0, left: 58 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = 440;
const AXIS_H = 26;

//: How much of the plot's height the hourly bars are allowed. They are the
//: ground and the climb is the figure: at a third, a busy hour is legible
//: without the bars competing with the curve for the top of the chart.
const BAR_ZONE = 0.34;

export function ActivityDayChart({
  start,
  end,
  timeZone,
  points,
  hours,
  goal,
  goalReachedAt = null,
  sleep = [],
}: {
  /** Local midnight to local midnight, so a quiet day is still a whole day. */
  start: string;
  end: string;
  timeZone: string;
  /** Cumulative steps, carried only at the minutes the climb bends on. */
  points: ClimbPoint[];
  hours: HourBar[];
  goal: number;
  goalReachedAt?: string | null;
  sleep?: SleepWindow[];
}) {
  const t0 = new Date(start).getTime();
  const t1 = new Date(end).getTime();
  const span = t1 - t0 || 1;
  const height = PAD.top + PLOT_H + AXIS_H;

  const total = points.length ? (points[points.length - 1]?.value ?? 0) : 0;
  // The goal is always on the axis, even on a day that got nowhere near it.
  // An axis that stops at 3,000 steps draws a triumphant-looking climb to the
  // top of the plot, which is the opposite of what happened.
  const top = Math.max(goal, total) * 1.05;
  const yTop = Math.max(2_000, Math.ceil(top / 2_000) * 2_000);

  const x = (at: string | number) =>
    PAD.left +
    Math.min(
      1,
      Math.max(0, ((typeof at === "number" ? at : new Date(at).getTime()) - t0) / span),
    ) *
      PLOT_W;
  const y = (steps: number) => PAD.top + PLOT_H - (steps / yTop) * PLOT_H;

  const busiest = Math.max(1, ...hours.map((hour) => hour.steps));
  const barHeight = (steps: number) => (steps / busiest) * (PLOT_H * BAR_ZONE);

  const hhmm = (ms: number) =>
    new Date(ms).toLocaleTimeString("en-AU", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone,
    });

  // On the hour in the wearer's own zone, labelled every second hour so a full
  // day carries twelve labels rather than twenty-four overlapping ones.
  const hourMarks: number[] = [];
  const first = new Date(t0);
  first.setMinutes(60, 0, 0);
  for (let t = first.getTime(); t <= t1; t += 3_600_000) hourMarks.push(t);
  const labelEvery = hourMarks.length > 14 ? 2 : 1;

  const gridStep = yTop / 5;
  const gridlines: number[] = [];
  for (let steps = 0; steps <= yTop; steps += gridStep) gridlines.push(steps);

  // The 24 hour slots the API bucketed into, laid out evenly. On the two days
  // a year that carry 23 or 25 hours the bars are off by one slot at one end;
  // that is a known and deliberate simplification, because the alternative -
  // positioning each bar from its own local offset - buys a correction nobody
  // can see against a bar whose own scale is already relative.
  const hourStart = (hour: number) => t0 + hour * 3_600_000;
  const slotWidth = PLOT_W / 24;

  // A crosshair column per hour: the cumulative total at the end of it, and
  // what that hour itself contributed.
  const climbAt = (ms: number): number | null => {
    let carried: number | null = null;
    for (const point of points) {
      if (new Date(point.at).getTime() > ms) break;
      carried = point.value;
    }
    return carried;
  };

  const columns: CrosshairColumn[] = hours.map((hour) => {
    const at = hourStart(hour.hour);
    const running = climbAt(at + 3_599_000);
    return {
      at: (PAD.left + (hour.hour + 0.5) * slotWidth) / W,
      title: `${hour.hour.toString().padStart(2, "0")}:00`,
      rows: [
        { label: "This hour", value: `${Math.round(hour.steps).toLocaleString()} steps` },
        {
          label: "Running total",
          value: running === null ? "—" : Math.round(running).toLocaleString(),
        },
      ],
    };
  });

  if (points.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-600">
        No minute-level steps recorded on this day.
      </p>
    );
  }

  const climb = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(point.at).toFixed(1)},${y(point.value).toFixed(1)}`)
    .join(" ");
  const last = points[points.length - 1]!;
  // Closed back along the baseline so the climb reads as accumulated ground
  // rather than as one more line among the day's signals.
  const area = `${climb} L${x(last.at).toFixed(1)},${y(0).toFixed(1)} L${x(points[0]!.at).toFixed(1)},${y(0).toFixed(1)} Z`;

  return (
    <Crosshair columns={columns}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Cumulative steps through the day from ${hhmm(t0)} to ${hhmm(t1)}, against a ${goal.toLocaleString()} step goal, with hourly totals beneath`}
      >
        {/* Sleep first, furthest back: it is the widest region on the chart. */}
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

        {gridlines.map((steps) => (
          <g key={steps}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(steps)}
              y2={y(steps)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={PAD.left - 8}
              y={y(steps)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {steps >= 1000 ? `${steps / 1000}k` : steps}
            </text>
          </g>
        ))}

        {hourMarks.map((t, index) =>
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

        {/* The hours, on their own scale along the bottom. They answer "when",
            and their height is relative to the day's busiest hour rather than
            to the step axis - at 800 steps against a 10,000 axis every bar
            would be one pixel tall. */}
        {hours.map((hour) => (
          <rect
            key={hour.hour}
            x={PAD.left + hour.hour * slotWidth + 2}
            y={PAD.top + PLOT_H - barHeight(hour.steps)}
            width={Math.max(1, slotWidth - 4)}
            height={Math.max(hour.steps > 0 ? 1 : 0, barHeight(hour.steps))}
            rx={2}
            fill="var(--viz-seq-2)"
          >
            <title>
              {`${hour.hour.toString().padStart(2, "0")}:00 — ${Math.round(hour.steps).toLocaleString()} steps`}
            </title>
          </rect>
        ))}

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(goal)}
          y2={y(goal)}
          stroke="var(--viz-axis)"
          strokeWidth={1.5}
          strokeDasharray="6 4"
          vectorEffect="non-scaling-stroke"
        />
        <text x={W - PAD.right + 6} y={y(goal) - 6} fontSize={11} fill="var(--viz-muted)">
          goal
        </text>

        <path d={area} fill="var(--viz-1)" fillOpacity={0.12} />
        <path
          d={climb}
          fill="none"
          stroke="var(--viz-1)"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />

        {/* The crossing, marked where it happened. It is the one instant on
            this chart worth naming, and reading it off two axes is exactly the
            arithmetic the cumulative shape exists to spare you. */}
        {goalReachedAt && (
          <g>
            <circle cx={x(goalReachedAt)} cy={y(goal)} r={4} fill="var(--viz-6)" />
            <text
              x={x(goalReachedAt) + 8}
              y={y(goal) - 10}
              fontSize={11}
              fill="var(--viz-6)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {hhmm(new Date(goalReachedAt).getTime())}
            </text>
          </g>
        )}

        <text
          x={Math.min(W - PAD.right + 4, x(last.at) + 8)}
          y={y(last.value) - 6}
          fontSize={11}
          fill="var(--viz-1)"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {Math.round(last.value).toLocaleString()}
        </text>

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={PAD.top + PLOT_H}
          y2={PAD.top + PLOT_H}
          stroke="var(--viz-axis)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
        {hourMarks.map((t, index) =>
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

/** The legend. Two marks in two units, which has to be said in words. */
export function DayLegend({ asleep }: { asleep: boolean }) {
  return (
    <ul className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
      <li className="flex items-center gap-1.5">
        <span
          aria-hidden
          className="h-0.5 w-4 rounded-full"
          style={{ backgroundColor: "var(--viz-1)" }}
        />
        Steps so far, against the left axis
      </li>
      <li className="flex items-center gap-1.5">
        <span
          aria-hidden
          className="size-2.5 rounded-sm"
          style={{ backgroundColor: "var(--viz-seq-2)" }}
        />
        Steps in each hour, scaled to the day&rsquo;s busiest
      </li>
      {asleep && (
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2.5 rounded-sm"
            style={{ backgroundColor: "var(--viz-sleep-band)" }}
          />
          Asleep
        </li>
      )}
    </ul>
  );
}
