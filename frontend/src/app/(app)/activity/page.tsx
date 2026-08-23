import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthActivityDay, HealthActivityHistory, HealthTrend } from "@/lib/api/types";

import { CalendarHeatmap } from "../charts";
import { Card, duration, Empty, num, PageHeader, shortDate, Stat } from "../ui";
import { ActivityDayChart, DayLegend } from "./ActivityDayChart";
import { ActivityTabs, WINDOWS } from "./ActivityTabs";
import { ActivityTrendChart, MasterLegend } from "./ActivityTrendChart";

export const dynamic = "force-dynamic";

/**
 * Activity, at whichever resolution the question needs.
 *
 * One master chart that changes with the window, rather than the four charts
 * of equal weight this page used to be: a year heatmap two-thirds blank, a
 * steps line, a weekly exercise bar chart with three bars in ninety days, and
 * a table of logged sessions every row of which read "0m". None of them
 * dominant, and three of them showing almost nothing.
 *
 * The question people bring here is "did I move enough, and how hard", and
 * those are two numbers rather than one. So the chart draws steps as height
 * and intensity as colour, and everything under it is that same answer in
 * numbers - which is support, not the subject.
 */

const TIME_ZONE = "Australia/Melbourne";

/**
 * The three overlays, on the master chart's shared axis.
 *
 * Colour is fixed per series so a line means the same thing between windows.
 * Resting heart rate keeps slot 8 because the heart and sleep pages already
 * fix it there - the same signal in three places should not change colour on
 * the way between them.
 */
const OVERLAYS = [
  { metric: "active_minutes", colour: "var(--viz-2)" },
  { metric: "vigorous_minutes", colour: "var(--viz-6)" },
  { metric: "resting_hr", colour: "var(--viz-8)" },
] as const;

export default async function ActivityPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string; date?: string }>;
}) {
  const { days: rawDays, date: rawDate } = await searchParams;
  const requested = Number(rawDays) || 30;
  const days = WINDOWS.some((w) => w.days === requested) ? requested : 30;

  if (days === 1) return <DayView date={rawDate ?? null} />;
  return <WindowView days={days} />;
}

/* -------------------------------------------------------------------------
 * One day
 * ---------------------------------------------------------------------- */

async function DayView({ date }: { date: string | null }) {
  // No date given means "the most recent day that has minute data", not today:
  // the intraday fetch only covers days Fitbit was asked for, and landing on
  // an empty plot is indistinguishable from landing on a broken page.
  const day = await serverGet<HealthActivityDay>(
    date ? `/health/activity/days/${date}` : "/health/activity/latest",
  );
  // For the day picker beneath the chart. It is the only way to know which
  // neighbouring days are worth offering.
  const history = await serverGet<HealthActivityHistory>("/health/activity?days=14&logged=false");

  const reached = day.goal_reached_at
    ? new Date(day.goal_reached_at).toLocaleTimeString("en-AU", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: TIME_ZONE,
      })
    : null;

  return (
    <>
      <PageHeader
        title="Activity"
        subtitle={
          day.count === 0
            ? `No minute-level steps recorded on ${shortDate(day.date)}.`
            : `Every minute of ${shortDate(day.date)} — ${day.count.toLocaleString()} readings.`
        }
      >
        <ActivityTabs current={1} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Steps"
          value={day.total == null ? null : Math.round(day.total).toLocaleString()}
          sub={
            day.total == null
              ? `goal ${day.goal.toLocaleString()}`
              : day.total >= day.goal
                ? `goal reached${reached ? ` at ${reached}` : ""}`
                : `${Math.round(day.goal - day.total).toLocaleString()} short of goal`
          }
          tone={
            day.total == null
              ? undefined
              : day.total >= day.goal
                ? "text-emerald-600 dark:text-emerald-400"
                : day.total < day.goal / 2
                  ? "text-rose-600 dark:text-rose-400"
                  : "text-amber-600 dark:text-amber-400"
          }
        />
        <Stat
          label="Distance"
          value={day.distance_km == null ? null : `${num(day.distance_km)} km`}
          sub="the watch's estimate"
        />
        <Stat
          label="Active"
          value={day.active_minutes == null ? null : `${Math.round(day.active_minutes)} min`}
          sub="moderate and vigorous"
        />
        <Stat
          label="Vigorous"
          value={day.vigorous_minutes == null ? null : `${Math.round(day.vigorous_minutes)} min`}
          sub="cardio and peak zones"
        />
      </div>

      <div className="space-y-4">
        <Card
          title={`Through ${shortDate(day.date)}`}
          subtitle="The climb is every step counted so far; the bars underneath are what each hour contributed. The grey stretches are time asleep."
        >
          <DayLegend asleep={day.sleep.length > 0} />
          <ActivityDayChart
            start={day.start}
            end={day.end}
            timeZone={TIME_ZONE}
            points={day.points}
            hours={day.hours}
            goal={day.goal}
            goalReachedAt={day.goal_reached_at ?? null}
            sleep={day.sleep}
          />
          {day.count === 0 && (
            <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
              No minute samples for this day. Intraday data needs a connected Fitbit with a Personal
              app registration, and the sync fetches it only for days that have none — so a day it
              skipped stays empty until the next sync covers it.
            </p>
          )}
        </Card>

        <Card title="Other days" subtitle="Days with a recorded step count, newest first.">
          <div className="flex flex-wrap gap-2 text-xs">
            {history.rows.slice(0, 14).map((row) => (
              <Link
                key={row.date}
                href={`/activity?days=1&date=${row.date}`}
                aria-current={row.date === day.date ? "true" : undefined}
                className={`rounded-md px-2 py-1 transition-colors ${
                  row.date === day.date
                    ? "bg-slate-900 font-medium text-white dark:bg-slate-100 dark:text-slate-900"
                    : "border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800"
                }`}
              >
                {shortDate(row.date)}
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------
 * A window of days
 * ---------------------------------------------------------------------- */

async function WindowView({ days }: { days: number }) {
  const end = new Date();
  const yearStart = new Date(end);
  yearStart.setUTCDate(yearStart.getUTCDate() - 364);
  const iso = (at: Date) => at.toISOString().slice(0, 10);

  const [history, stepsYear] = await Promise.all([
    serverGet<HealthActivityHistory>(`/health/activity?days=${days}`),
    serverGet<HealthTrend>(
      `/health/trend?metric=steps&start=${iso(yearStart)}&end=${iso(end)}&window=7`,
    ),
  ]);

  const { summary, logged } = history;
  const byMetric = new Map(history.series.map((one) => [one.metric, one]));
  const overlays = OVERLAYS.flatMap((row) => {
    const series = byMetric.get(row.metric);
    return series
      ? [{ label: series.label, unit: series.unit, points: series.points, colour: row.colour }]
      : [];
  });

  const stepsByDate = Object.fromEntries(stepsYear.points.map((p) => [p.date, Math.round(p.value)]));

  return (
    <>
      <PageHeader
        title="Activity"
        subtitle={
          summary.days_recorded === 0
            ? `Nothing recorded in the last ${days} days.`
            : `${summary.days_recorded} day${summary.days_recorded === 1 ? "" : "s"} with a step count in ${summary.days_elapsed}. Every average below is over those days, not the days between them.`
        }
      >
        <ActivityTabs current={days} />
      </PageHeader>

      {summary.days_recorded === 0 ? (
        <Card>
          <Empty>Nothing recorded in this window. Sync the watch, or widen the range.</Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* The chart leads. It is the only thing on the page that answers
              "am I moving enough" in one look; the tiles beneath it are the
              same answer in numbers. */}
          <Card
            title="Every day in the window"
            subtitle="One scale for all of it: 200 steps is one unit, so a gridline is 2,000 steps, ten minutes and ten bpm at once. Gaps are days with no recording."
          >
            <MasterLegend overlays={overlays} />
            <ActivityTrendChart
              start={history.start}
              end={history.end}
              goal={history.goal}
              bars={history.bars.map((bar) => ({
                date: bar.date,
                steps: bar.steps,
                activeMinutes: bar.active_minutes ?? null,
                band: bar.band ?? null,
              }))}
              trailing={history.trailing}
              overlays={overlays}
            />
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Height is how far you went and colour is how hard: a tall pale bar is a day of
              pottering that happened to cover ground, which was an identical mark to a real walk
              before. The three lines share the bars&rsquo; axis because each of them lives inside
              0–100 in its own unit — which makes their crossings real, and also means resting
              heart rate moving 62 to 68 is six percent of this axis and reads nearly flat. The gap
              between active and vigorous minutes is the one worth watching.
            </p>
          </Card>

          {/* The four numbers that answer "how am I doing", stated as
              comparisons rather than as bare values - an average step count on
              its own is a number nobody can act on. */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="Typical day"
              value={
                summary.mean_steps == null ? null : Math.round(summary.mean_steps).toLocaleString()
              }
              sub={`steps over ${summary.days_recorded} recorded day${summary.days_recorded === 1 ? "" : "s"} — goal ${history.goal.toLocaleString()}`}
              tone={
                (summary.mean_steps ?? 0) >= history.goal
                  ? "text-emerald-600 dark:text-emerald-400"
                  : (summary.mean_steps ?? 0) < 4_000
                    ? "text-rose-600 dark:text-rose-400"
                    : "text-amber-600 dark:text-amber-400"
              }
            />
            <Stat
              label="Active minutes"
              value={
                summary.active_per_week == null
                  ? null
                  : `${Math.round(summary.active_per_week)}/wk`
              }
              sub={`over ${summary.active_days} day${summary.active_days === 1 ? "" : "s"} — WHO asks 150–300`}
              tone={
                summary.active_per_week == null
                  ? undefined
                  : summary.active_per_week >= 150
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-amber-600 dark:text-amber-400"
              }
            />
            <Stat
              label="Vigorous minutes"
              value={
                summary.vigorous_per_week == null
                  ? null
                  : `${Math.round(summary.vigorous_per_week)}/wk`
              }
              sub={`over ${summary.vigorous_days} day${summary.vigorous_days === 1 ? "" : "s"} — WHO asks 75–150`}
              tone={
                summary.vigorous_per_week == null
                  ? undefined
                  : summary.vigorous_per_week >= 75
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-amber-600 dark:text-amber-400"
              }
            />
            <Stat
              label="Sitting"
              value={
                summary.mean_sitting_hours == null
                  ? null
                  : `${num(summary.mean_sitting_hours)} h`
              }
              sub={`waking hours per day, over ${summary.sitting_days} day${summary.sitting_days === 1 ? "" : "s"}`}
            />
          </div>

          <Card
            title="Every day, scored"
            subtitle="Coloured the way the heatmap is: greener is better, against the same published thresholds. Hover a heading for the evidence behind it."
          >
            <div className="overflow-x-auto">
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead>
                  <tr>
                    <th className="border-b border-slate-200 px-2 py-2 text-left text-xs font-semibold dark:border-slate-800">
                      Day
                    </th>
                    {history.columns.map((column) => (
                      <th
                        key={column.key}
                        title={column.evidence}
                        className="whitespace-nowrap border-b border-slate-200 px-2 py-2 text-center text-xs font-semibold dark:border-slate-800"
                      >
                        {column.label}
                        {column.unit && (
                          <span className="ml-1 font-normal text-slate-400 dark:text-slate-600">
                            {column.unit}
                          </span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-slate-900 dark:text-slate-100">
                  {history.rows.map((row) => (
                    <tr key={row.date}>
                      <td className="whitespace-nowrap border-b border-slate-100 px-2 py-1 dark:border-slate-800/60">
                        <Link
                          href={`/activity?days=1&date=${row.date}`}
                          className="hover:underline"
                        >
                          {shortDate(row.date)}
                        </Link>
                      </td>
                      {row.cells.map((cell, index) => {
                        const column = history.columns[index];
                        if (!column) return null;
                        return (
                          <td
                            key={cell.key}
                            className="border-b border-l border-slate-100 px-2 py-1 text-center text-xs tabular-nums dark:border-slate-800/60"
                            style={{
                              backgroundColor: cell.band
                                ? `var(--viz-score-${cell.band})`
                                : undefined,
                            }}
                            title={`${column.label} — ${shortDate(row.date)}: ${
                              cell.value === null || cell.value === undefined
                                ? "no reading"
                                : `${num(cell.value, column.places)}${column.unit}`
                            }${column.scored ? "" : " (shown but not scored)"}`}
                          >
                            {cell.value === null || cell.value === undefined
                              ? "—"
                              : num(cell.value, column.places)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ol className="mt-3 flex flex-wrap gap-2">
              {["poor", "below par", "fair", "good", "excellent"].map((label, index) => (
                <li key={label} className="flex items-center gap-1.5 text-xs">
                  <span
                    aria-hidden
                    className="inline-block size-3.5 rounded-sm"
                    style={{ backgroundColor: `var(--viz-score-${index + 1})` }}
                  />
                  {label}
                </li>
              ))}
              <li className="text-xs text-slate-500 dark:text-slate-400">
                Distance, light minutes, sitting and calories are shown uncoloured on purpose: no
                guideline is written in kilometres, light activity is not what the WHO target
                counts, sitting here is an estimate resting on another estimate, and most of a
                day&rsquo;s burn is basal metabolic rate.
              </li>
            </ol>
          </Card>

          <Card
            title="Steps, past year"
            subtitle="Darker is more. A blank square is a day the watch recorded nothing, not a day of no steps."
          >
            <CalendarHeatmap
              values={stepsByDate}
              start={iso(yearStart)}
              end={iso(end)}
              unit="steps"
              emptyLabel="no data"
            />
          </Card>

          {logged && logged.sessions > 0 && (
            <Card
              title="Logged sessions"
              subtitle={`What was hand-logged over the same ${days} days — ${logged.sessions} session${logged.sessions === 1 ? "" : "s"}, ${duration(logged.minutes)} in total.`}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                    <th className="pb-2 text-left font-normal">Session</th>
                    <th className="pb-2 text-right font-normal">Times</th>
                    <th className="pb-2 text-right font-normal">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {logged.by_type.map((type) => (
                    <tr
                      key={type.name}
                      className="border-b border-slate-100 dark:border-slate-800/60"
                    >
                      <td className="max-w-0 truncate py-1.5" title={type.name}>
                        {type.name}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">{type.count}</td>
                      <td className="py-1.5 text-right tabular-nums text-slate-500">
                        {duration(type.minutes)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
