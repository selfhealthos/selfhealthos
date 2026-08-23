import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthSleepHistory, HealthTrend } from "@/lib/api/types";

import { Card, duration, Empty, num, PageHeader, shortDate } from "../ui";
import { MasterLegend, SleepTrendChart } from "./SleepTrendChart";
import { SleepTabs, WINDOWS } from "./SleepTabs";

export const dynamic = "force-dynamic";

/**
 * Sleep over a window: is this typical, and is it getting better?
 *
 * The other half of the split - `sleep/[date]` answers "how did I sleep last
 * night". Keeping both on one page was the original problem: thirty days of
 * trend and one night's detail want opposite layouts, and trying to serve both
 * made every chart on the page too small to read and gave none of them any
 * more weight than the rest.
 *
 * What this page is *for* is a comparison against two references: the target,
 * and this sleeper's own recent nights. So the target is a line across the
 * chart rather than a number in a caption, and every average states how many
 * nights it is over — with 13 nights recorded in 30, an average presented as
 * "your month" would be a quiet lie.
 */

/**
 * The four overnight signals, on the master chart's shared 0-100 axis.
 *
 * They are in four different units and are plotted together because each one
 * happens to live inside 0-100 in its own - the same argument the trends
 * page's recovery panel makes, and the only condition under which a shared
 * axis is honest. Colour comes from the categorical slots in fixed order.
 *
 * No shaded normal bands here, deliberately: a band belongs to one series, and
 * shading 95-100 across a plot carrying three other lines would look like it
 * applied to all of them. The per-signal scales on the night page keep theirs.
 */
const OVERLAYS = [
  { metric: "resting_hr", label: "Resting heart rate", unit: "bpm", colour: "var(--viz-8)" },
  { metric: "hrv_rmssd", label: "HRV", unit: "ms", colour: "var(--viz-3)" },
  { metric: "breathing_rate", label: "Breathing rate", unit: "/min", colour: "var(--viz-7)" },
  { metric: "spo2_min", label: "Lowest blood oxygen", unit: "%", colour: "var(--viz-1)" },
] as const;

export default async function SleepPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const requested = Number(raw) || 30;
  const days = WINDOWS.some((w) => w.days === requested) ? requested : 30;

  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  const iso = (at: Date) => at.toISOString().slice(0, 10);

  const [history, trends] = await Promise.all([
    serverGet<HealthSleepHistory>(`/health/sleep?days=${days}`),
    serverGet<HealthTrend[]>(
      `/health/trends?metrics=resting_hr,hrv_rmssd,breathing_rate,spo2_min` +
        `&start=${iso(start)}&end=${iso(end)}&window=7`,
    ),
  ]);

  const { sessions, summary } = history;
  const byMetric = new Map(trends.map((t) => [t.metric, t]));
  const points = (metric: string) =>
    (byMetric.get(metric)?.points ?? []).map((p) => ({ date: p.date, value: p.value }));

  const target = summary.target_minutes;
  //: Null and undefined both mean "not enough nights to say"; collapsing them
  //: here keeps every use below from having to check twice.
  const shortfall = summary.mean_shortfall_minutes ?? null;
  const spread = summary.bedtime_spread_minutes ?? null;
  const changed = summary.previous;

  return (
    <>
      <PageHeader
        title="Sleep"
        subtitle={
          summary.nights_recorded === 0
            ? `No nights recorded in the last ${days} days.`
            : `${summary.nights_recorded} night${summary.nights_recorded === 1 ? "" : "s"} recorded in ${summary.days_elapsed} days. Every average below is over those nights, not the days between them.`
        }
      >
        <SleepTabs current={days} latestNight={sessions[0]?.local_date ?? null} />
      </PageHeader>

      {summary.nights_recorded === 0 ? (
        <Card>
          <Empty>Nothing recorded in this window. Sync the watch, or widen the range.</Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* The three numbers that answer "how am I doing", stated as
              comparisons rather than as bare values - an average duration on
              its own is a number nobody can act on. */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Summary
              label="Typical night"
              value={
                summary.mean_duration_minutes === null ||
                summary.mean_duration_minutes === undefined
                  ? "—"
                  : duration(summary.mean_duration_minutes)
              }
              detail={
                shortfall === null
                  ? `over ${summary.nights_recorded} nights`
                  : Math.abs(shortfall) < 5
                    ? `on your ${duration(target)} target`
                    : shortfall < 0
                      ? `${duration(Math.abs(shortfall))} short of your ${duration(target)} target, per night`
                      : `${duration(shortfall)} over your ${duration(target)} target, per night`
              }
              tone={shortfall !== null && shortfall < -30 ? "text-amber-600 dark:text-amber-400" : ""}
            />
            <Summary
              label="On target"
              value={`${summary.nights_on_target} of ${summary.nights_recorded}`}
              detail={`nights within half an hour of ${duration(target)}`}
            />
            <Summary
              label="Bedtime consistency"
              value={spread === null ? "—" : `±${spread}m`}
              detail={
                spread === null
                  ? "needs a few more nights"
                  : spread <= 45
                    ? "you go to bed at a consistent hour"
                    : "your bedtime moves around a lot"
              }
              tone={spread !== null && spread > 60 ? "text-amber-600 dark:text-amber-400" : ""}
            />
          </div>

          {/* The chart leads. It is the only thing on the page that answers
              "how is my sleep" in one look; the tiles above it are the same
              answer in numbers, which is support rather than the subject. */}
          <Card
            title="Every night in the window"
            subtitle="One scale for all of it: an hour of sleep is ten units, so a gridline is an hour, ten bpm, ten ms and ten points of oxygen at once. Gaps are nights with no recording."
          >
            <MasterLegend overlays={OVERLAYS.map((row) => ({ ...row, points: points(row.metric) }))} />
            <SleepTrendChart
              start={iso(start)}
              end={iso(end)}
              targetMinutes={target}
              nights={sessions
                .map((session) => ({
                  date: session.local_date,
                  minutes: session.duration_minutes,
                  efficiency: session.efficiency ?? null,
                  hasHypnogram: session.has_hypnogram,
                }))
                .reverse()}
              overlays={OVERLAYS.map((row) => ({ ...row, points: points(row.metric) }))}
            />
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Everything shares one date axis, so a short night and a raised resting heart rate
              above it are the same evening. The four signals are in different units and are
              plotted together because each of them lives inside 0–100 in its own — which means
              their crossings are real, but also that blood oxygen moving 93 to 97 is four percent
              of this axis and reads nearly flat. Open a night for that signal at its own scale.
            </p>
          </Card>

          {changed.comparable && (
            <Card
              title="What changed"
              subtitle={`Against the previous ${summary.days_elapsed} days, which held ${changed.nights_recorded} recorded nights.`}
            >
              <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                <Delta
                  label="Time asleep"
                  minutes={changed.duration_delta_minutes}
                  format={(value) => duration(Math.abs(value))}
                />
                <Delta
                  label="Efficiency"
                  minutes={changed.efficiency_delta}
                  format={(value) => `${num(Math.abs(value), 0)}%`}
                />
              </div>
              {/* The interpretation, not just the arrows: improving quality
                  with falling duration is the common pattern and the one most
                  easily misread as "getting better". */}
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                {sentence(changed.duration_delta_minutes, changed.efficiency_delta)}
              </p>
            </Card>
          )}

          <Card
            title="Recent nights"
            subtitle="Coloured the way the heatmap is: greener is better, against the same published thresholds. Open a night for its hypnogram."
          >
            <div className="overflow-x-auto">
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead>
                  <tr>
                    <th className="border-b border-slate-200 px-2 py-2 text-left text-xs font-semibold dark:border-slate-800">
                      Night
                    </th>
                    <th className="border-b border-slate-200 px-2 py-2 text-right text-xs font-semibold dark:border-slate-800">
                      vs target
                    </th>
                    {history.columns.map((column) => (
                      <th
                        key={column.key}
                        // The evidence for every threshold is one hover away,
                        // as on the heatmap: a colour that cannot say why it
                        // is red is decoration.
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
                  {sessions.map((session) => {
                    const delta = session.duration_minutes - target;
                    return (
                      <tr key={session.id}>
                        <td className="whitespace-nowrap border-b border-slate-100 px-2 py-1 dark:border-slate-800/60">
                          <Link
                            href={`/sleep/${session.local_date}`}
                            className="hover:underline"
                          >
                            {shortDate(session.local_date)}
                          </Link>
                          {!session.has_hypnogram && (
                            <span className="ml-1.5 text-xs text-slate-400 dark:text-slate-600">
                              totals only
                            </span>
                          )}
                        </td>
                        <td
                          className={`border-b border-slate-100 px-2 py-1 text-right text-xs tabular-nums dark:border-slate-800/60 ${
                            delta >= -30
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-amber-600 dark:text-amber-400"
                          }`}
                        >
                          {delta >= 0 ? "+" : "−"}
                          {duration(Math.abs(delta))}
                        </td>
                        {session.cells.map((cell, index) => {
                          const column = history.columns[index];
                          if (!column) return null;
                          return (
                            <td
                              key={cell.key}
                              className="border-b border-l border-slate-100 px-2 py-1 text-center text-xs tabular-nums dark:border-slate-800/60"
                              style={{ backgroundColor: cell.band ? `var(--viz-score-${cell.band})` : undefined }}
                              title={`${column.label} — ${shortDate(session.local_date)}: ${
                                cell.value === null || cell.value === undefined
                                  ? "no reading"
                                  : `${num(cell.value, column.places)}${column.unit}`
                              }`}
                            >
                              {cell.value === null || cell.value === undefined
                                ? "—"
                                : num(cell.value, column.places)}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
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
            </ol>
          </Card>
        </div>
      )}
    </>
  );
}

/** One comparison, stated as a sentence rather than a bare figure. */
function Summary({
  label,
  value,
  detail,
  tone = "",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="mb-1 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-500">
        {label}
      </p>
      <p className={`text-2xl font-bold ${tone}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p>
    </div>
  );
}

function Delta({
  label,
  minutes,
  format,
}: {
  label: string;
  minutes: number | null | undefined;
  format: (value: number) => string;
}) {
  if (minutes === null || minutes === undefined) return null;
  const up = minutes > 0;
  const flat = Math.abs(minutes) < 1;
  return (
    <div>
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="tabular-nums">
        {flat ? "unchanged" : `${up ? "↑" : "↓"} ${format(minutes)}`}
      </p>
    </div>
  );
}

/**
 * The one interpretation worth spelling out.
 *
 * Sleeping better but less is the pattern people misread as improvement, so it
 * gets said in words rather than left as two arrows pointing opposite ways.
 */
function sentence(durationDelta: number | null | undefined, efficiencyDelta: number | null | undefined): string {
  const d = durationDelta ?? 0;
  const e = efficiencyDelta ?? 0;
  if (d < -10 && e > 1) {
    return "You are sleeping more soundly but for less time — the quality is up, the opportunity is down.";
  }
  if (d > 10 && e < -1) {
    return "You are spending longer asleep but sleeping less soundly through it.";
  }
  if (d > 10 && e >= -1) return "More sleep than the previous window, at the same quality or better.";
  if (d < -10) return "Less sleep than the previous window.";
  return "Much the same as the previous window.";
}
