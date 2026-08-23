import { serverGet } from "@/lib/api/server";
import type { HealthBristolDaily, HealthTrend } from "@/lib/api/types";

import { LineChart, StackedColumnChart } from "../charts";
import { Card, duration, num, PageHeader, RangeTabs } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Trends: every metric worth watching, over one window.
 *
 * Ported from the one-data dashboard's `trends.html`. The shape kept is the
 * small-multiple grid, where every panel shares the same window so a dip in one
 * lines up with a dip in another by position.
 *
 * **The form follows the measurement, not a house style.** A level that moves
 * continuously is a line; a quantity accumulated over a day is a column, because
 * the day is a bucket and a line between buckets implies values in between that
 * nobody measured; a quantity made of parts is a stacked column, because the
 * parts are the story.
 *
 * **Never two y-axes.** The recovery panel below puts three series on one
 * shared scale, which works only because they happen to share a numeric range
 * (roughly 40–80). Where scales genuinely differ, the answer is two panels, not
 * two axes - the crossing point of two differently-scaled lines is an artefact
 * of the scaling and means nothing at all.
 */

//: Panels drawn as a single line: a level, measured at a moment, that moves
//: continuously between measurements.
const LINE_PANELS: ReadonlyArray<{
  metric: string;
  title: string;
  hint?: string;
  zeroBased?: boolean;
  reference?: { value: number; label: string };
}> = [
  { metric: "sleep_efficiency", title: "Sleep efficiency", hint: "goal 85%+" },
  { metric: "weight_kg", title: "Weight" },
  // No `bristol_mean` panel: the stacked column below shows the same days in
  // more detail, and a daily mean of 4 is indistinguishable from one 3 and one
  // 5 - which is the distinction the whole page is for.
];

//: Panels drawn as columns: a quantity accumulated over a day.
const COLUMN_PANELS: ReadonlyArray<{
  metric: string;
  title: string;
  hint?: string;
  color: string;
  reference?: { value: number; label: string };
}> = [
  {
    metric: "exercise_minutes",
    title: "Exercise logged",
    hint: "minutes per day",
    color: "var(--viz-3)",
  },
  {
    metric: "gym_volume_kg",
    title: "Gym volume",
    hint: "weight × reps, per day",
    color: "var(--viz-5)",
  },
];

//: The three recovery signals, on one shared axis. They are in different units
//: - milliseconds, beats per minute, ml/kg/min - and that is stated on the
//: panel, because a shared axis with mixed units is only honest if it says so.
const RECOVERY = [
  { metric: "hrv_rmssd", label: "HRV (RMSSD) — ms", color: "var(--viz-1)" },
  { metric: "resting_hr", label: "Resting heart rate — bpm", color: "var(--viz-2)" },
  { metric: "vo2max", label: "VO2 max — ml/kg/min", color: "var(--viz-3)" },
] as const;

const SLEEP_STAGES = [
  { metric: "sleep_deep_minutes", label: "Deep", color: "var(--viz-stage-deep)" },
  { metric: "sleep_rem_minutes", label: "REM", color: "var(--viz-stage-rem)" },
  { metric: "sleep_light_minutes", label: "Light", color: "var(--viz-stage-light)" },
] as const;

const BRISTOL_MEANING = [
  "Separate hard lumps — constipation",
  "Lumpy and sausage-like — constipation",
  "Sausage with cracks — ideal",
  "Smooth and soft — ideal",
  "Soft blobs — lacking fibre",
  "Mushy — loose",
  "Liquid — diarrhoea",
];

const RANGES = [
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
  { days: 365, label: "1y" },
  { days: 1095, label: "3y" },
] as const;

export default async function TrendsPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 90;

  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  const iso = (at: Date) => at.toISOString().slice(0, 10);

  const wanted = [
    ...LINE_PANELS.map((p) => p.metric),
    ...COLUMN_PANELS.map((p) => p.metric),
    ...RECOVERY.map((r) => r.metric),
    ...SLEEP_STAGES.map((s) => s.metric),
    "steps",
  ];

  const [trends, bristol] = await Promise.all([
    serverGet<HealthTrend[]>(
      `/health/trends?metrics=${wanted.join(",")}&start=${iso(start)}&end=${iso(end)}&window=7`,
    ),
    // Bristol counts by score cannot come from `DailyMetric` - that table holds
    // one scalar per metric per day, and "two 4s and a 6" is three numbers.
    serverGet<HealthBristolDaily>(`/health/bristol?days=${days}`),
  ]);
  const byMetric = new Map(trends.map((t) => [t.metric, t]));

  /** A metric's points as a date→value map, for the column charts. */
  const valuesOf = (metric: string, scale = 1): Record<string, number> =>
    Object.fromEntries(
      (byMetric.get(metric)?.points ?? []).map((p) => [p.date, p.value * scale]),
    );

  /** Every date any of these metrics has a value for, ascending. */
  const datesAcross = (metrics: readonly string[]): string[] =>
    [
      ...new Set(metrics.flatMap((m) => (byMetric.get(m)?.points ?? []).map((p) => p.date))),
    ].sort();

  const sleepDates = datesAcross(SLEEP_STAGES.map((s) => s.metric));
  const stepDates = datesAcross(["steps"]);
  const steps = byMetric.get("steps");

  const bristolDates = bristol.points.map((p) => p.date);
  const bristolLayers = BRISTOL_MEANING.map((meaning, index) => ({
    label: `${index + 1} — ${meaning}`,
    color: `var(--viz-div-${index + 1})`,
    values: Object.fromEntries(
      bristol.points
        .filter((p) => (p.counts[index] ?? 0) > 0)
        .map((p) => [p.date, p.counts[index] ?? 0]),
    ),
  }));

  return (
    <>
      <PageHeader
        title="Trends"
        subtitle={`Daily values over ${days} days. Lines are levels; columns are per-day quantities.`}
      >
        <RangeTabs basePath="/trends" current={days} options={RANGES} />
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card
          title="Recovery signals"
          subtitle="HRV, resting heart rate and VO2 max on one axis. Different units — see the legend — plotted together because they share a numeric range and are read against each other."
        >
          <LineChart
            series={RECOVERY.map((row) => ({
              label: row.label,
              points: (byMetric.get(row.metric)?.points ?? []).map((p) => ({
                date: p.date,
                value: p.value,
              })),
            }))}
            height={220}
          />
          <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
            {RECOVERY.map((row) => {
              const trend = byMetric.get(row.metric);
              return (
                <div key={row.metric}>
                  <dt className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                    <span
                      aria-hidden
                      className="h-0.5 w-3 rounded-full"
                      style={{ backgroundColor: row.color }}
                    />
                    {row.label.split(" — ")[0]}
                  </dt>
                  <dd className="tabular-nums">
                    {trend?.mean ? `${num(trend.mean)} ${trend.unit} avg` : "no data"}
                  </dd>
                </div>
              );
            })}
          </dl>
        </Card>

        <Card
          title="Time asleep"
          subtitle="Hours per night, split by stage. Seven hours of mostly light sleep and seven with a proper deep block are the same number and a different night."
        >
          <StackedColumnChart
            dates={sleepDates}
            // Minutes to hours here rather than in the API: the stored metric is
            // minutes, every other consumer wants minutes, and only this chart
            // reads in hours.
            layers={SLEEP_STAGES.map((stage) => ({
              label: stage.label,
              color: stage.color,
              values: valuesOf(stage.metric, 1 / 60),
            }))}
            height={220}
            unit="h"
            stackLabel={(total) => duration(total * 60)}
            reference={{ value: 7.5, label: "7.5h" }}
          />
        </Card>

        <Card
          title="Steps"
          subtitle={
            steps?.mean
              ? `${Math.round(steps.mean).toLocaleString()} per day on average · best ${Math.round(steps.maximum ?? 0).toLocaleString()}`
              : "Steps per day."
          }
        >
          <StackedColumnChart
            dates={stepDates}
            layers={[{ label: "Steps", color: "var(--viz-1)", values: valuesOf("steps") }]}
            height={220}
            unit="steps"
            reference={{ value: 10_000, label: "goal" }}
          />
        </Card>

        <Card
          title="Bristol score"
          subtitle="How many of each score per day. Cool is hard, warm is loose, neutral is the healthy middle."
        >
          <StackedColumnChart
            dates={bristolDates}
            layers={bristolLayers}
            height={220}
            unit="observations"
            stackLabel={(total) => `${total} observation${total === 1 ? "" : "s"}`}
          />
        </Card>

        {LINE_PANELS.map((panel) => {
          const trend = byMetric.get(panel.metric);
          const points = trend?.points ?? [];
          return (
            <Card
              key={panel.metric}
              title={panel.title}
              subtitle={
                points.length > 0
                  ? `${num(trend?.mean)} ${trend?.unit} average · ${num(trend?.minimum)}–${num(trend?.maximum)} · ${points.length} days`
                  : (panel.hint ?? "")
              }
            >
              <LineChart
                series={[
                  {
                    label: panel.title,
                    points: points.map((p) => ({ date: p.date, value: p.value })),
                  },
                ]}
                height={190}
                unit={trend?.unit ?? ""}
                zeroBased={panel.zeroBased}
                reference={panel.reference}
              />
            </Card>
          );
        })}

        {COLUMN_PANELS.map((panel) => {
          const trend = byMetric.get(panel.metric);
          return (
            <Card
              key={panel.metric}
              title={panel.title}
              subtitle={
                trend && trend.count > 0
                  ? `${num(trend.mean)} ${trend.unit} on the days it happened · ${trend.count} days`
                  : (panel.hint ?? "")
              }
            >
              <StackedColumnChart
                dates={datesAcross([panel.metric])}
                layers={[
                  { label: panel.title, color: panel.color, values: valuesOf(panel.metric) },
                ]}
                height={190}
                unit={trend?.unit ?? ""}
                reference={panel.reference}
              />
            </Card>
          );
        })}
      </div>

      {trends.length === 0 && bristol.points.length === 0 && (
        <p className="mt-6 text-center text-sm text-slate-400 dark:text-slate-600">
          No daily metrics in this window. Sync a wearable or log an entry, then come back.
        </p>
      )}
    </>
  );
}
