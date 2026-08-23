import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, serverGet } from "@/lib/api/server";
import type { HealthNight } from "@/lib/api/types";

import { NightStack, StageLegend } from "../../nightcharts";
import { Card, clock, duration, Empty, num, PageHeader, shortDate } from "../../ui";
import { NightPager } from "../NightPager";
import { SleepTabs } from "../SleepTabs";

export const dynamic = "force-dynamic";

/**
 * One night, as a report rather than a dashboard.
 *
 * The page answers four questions in the order a person actually asks them:
 * how long did I sleep, was that good, what happened during it, and is
 * anything worth looking at. Everything is stated against a reference - the
 * target, or this sleeper's own recent nights - because a duration on its own
 * is a number nobody can act on. Seven hours is a good night for one person
 * and a short one for the next.
 *
 * The verdict sentence comes from the backend (`nights.verdict`) and is
 * rule-based, so the same night always reads the same way and every claim in
 * it traces to a threshold in `scoring.py` or `nights.py`. It is the one part
 * of the page people will read *instead of* the charts, which is exactly why
 * it is not allowed to be generated prose.
 *
 * **Fitbit is not a sleep study.** Stages are inferred from movement and heart
 * rate; SpO2 is a reflectance estimate averaged into one-minute buckets. That
 * caveat is on the page rather than in this comment, because the person
 * reading a red dip needs it more than the person reading the source.
 */

const SPO2_NORMAL = { from: 95, to: 100 };
const SPO2_THRESHOLD = { value: 90, label: "90%" };

const STATE_STYLES: Record<string, { mark: string; tone: string }> = {
  ok: { mark: "✓", tone: "text-emerald-600 dark:text-emerald-400" },
  watch: { mark: "!", tone: "text-amber-600 dark:text-amber-400" },
  concern: { mark: "⚠", tone: "text-rose-600 dark:text-rose-400" },
};

export default async function NightPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;

  let night: HealthNight;
  try {
    night = await serverGet<HealthNight>(`/health/nights/${date}`);
  } catch (error) {
    // A date with no session is a 404 from the API and a 404 here. An empty
    // hypnogram and a night that was never recorded are different answers.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const { session, architecture: arch, oxygen, heart, series, timezone, baseline, verdict } = night;
  const hr = series.hr ?? [];
  const spo2 = series.spo2 ?? [];
  const nadir = oxygen.minimum ?? null;
  const target = baseline.target_minutes;
  const targetDelta = verdict.target_delta_minutes ?? 0;

  const marks = oxygen.dips.map((dip) => ({
    from: dip.started_at,
    to: dip.ended_at,
    label: `−${dip.drop} points to ${dip.lowest}% at ${clock(dip.started_at, timezone)}`,
  }));

  return (
    <>
      <PageHeader
        title={shortDate(night.date)}
        subtitle={`Asleep ${clock(session.started_at, timezone)} to ${clock(session.ended_at, timezone)}`}
      >
        {/* Paging first, then the view switch. The arrows change *which*
            night; the tabs change what is being asked of it. */}
        <div className="flex flex-col items-end gap-1.5">
          <NightPager previous={night.neighbours.previous} next={night.neighbours.next} />
          {/* The tab has to point at the real newest night, not this one:
              after paging back a week, "Last night" linking to the page you
              are already on is a dead control. */}
          <SleepTabs current="night" latestNight={night.neighbours.latest ?? night.date} />
        </div>
      </PageHeader>

      <div className="space-y-4">
        {/* The hero. One number, large, with its two references underneath —
            everything else on the page is subordinate to this. */}
        <section className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-5xl font-bold tabular-nums sm:text-6xl">
                {duration(session.duration_minutes)}
              </p>
              <p className="mt-2 text-lg font-medium">{verdict.headline}</p>
              <p className="mt-1 max-w-prose text-sm text-slate-500 dark:text-slate-400">
                {verdict.detail}
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">vs target</dt>
                <dd
                  className={`tabular-nums ${
                    targetDelta >= -30
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-amber-600 dark:text-amber-400"
                  }`}
                >
                  {targetDelta >= 0 ? "+" : "−"}
                  {duration(Math.abs(targetDelta))}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">
                  vs your {baseline.days} days
                </dt>
                <dd className="tabular-nums">
                  {verdict.delta_minutes === null || verdict.delta_minutes === undefined ? (
                    // Below five recorded nights there is no personal norm to
                    // compare against, and saying so beats inventing one.
                    <span className="text-slate-400 dark:text-slate-600">
                      {baseline.nights_recorded} nights recorded
                    </span>
                  ) : (
                    <>
                      {verdict.delta_minutes >= 0 ? "↑ " : "↓ "}
                      {duration(Math.abs(verdict.delta_minutes))}
                    </>
                  )}
                </dd>
              </div>
            </dl>
          </div>

          {/* Time asleep against the target, as a bar rather than a sentence. */}
          <div className="mt-5">
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <span
                className="absolute inset-y-0 left-0 rounded-full"
                style={{
                  width: `${Math.min(100, (session.duration_minutes / target) * 100)}%`,
                  backgroundColor:
                    targetDelta >= -30 ? "var(--viz-score-5)" : "var(--viz-score-3)",
                }}
              />
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Target {duration(target)}
              {baseline.mean_duration_minutes !== null &&
                baseline.mean_duration_minutes !== undefined &&
                ` · your ${baseline.days}-day average is ${duration(baseline.mean_duration_minutes)} over ${baseline.nights_recorded} recorded nights`}
            </p>
          </div>
        </section>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {/* The timeline takes the full width. It is the reason the page
              exists, and squeezed into two of three columns the hours were
              narrower than the stage blocks drawn on them. */}
          <Card
            className="xl:col-span-3"
            title="The night"
            subtitle="Stages, heart rate and blood oxygen on one clock. Red bands mark oxygen dips — read them straight up and down."
          >
            {night.has_hypnogram || hr.length > 0 || spo2.length > 0 ? (
              <>
                <StageLegend />
                <NightStack
                  start={session.started_at}
                  end={session.ended_at}
                  timeZone={timezone}
                  segments={night.segments}
                  marks={marks}
                  panels={[
                    { label: "Heart rate", unit: "bpm", points: hr, colour: "var(--viz-8)", step: 10 },
                    {
                      label: "Blood oxygen",
                      unit: "%",
                      points: spo2,
                      colour: "var(--viz-1)",
                      normalBand: SPO2_NORMAL,
                      reference: SPO2_THRESHOLD,
                      step: 2,
                    },
                  ]}
                />
                <p className="mt-2 flex justify-between text-xs text-slate-500 dark:text-slate-400">
                  <span>Asleep {clock(session.started_at, timezone)}</span>
                  <span>Awake {clock(session.ended_at, timezone)}</span>
                </p>
              </>
            ) : (
              <Empty>
                No chronology for this night — only totals. Stage segments and overnight SpO2
                exist for nights synced since the app started storing them.
              </Empty>
            )}
          </Card>

          <div className="space-y-4">
            <Card title="Signals" subtitle="Each against its clinical normal range.">
              {night.signals.length === 0 ? (
                <Empty>Nothing measured beyond duration.</Empty>
              ) : (
                <ul className="space-y-2.5">
                  {night.signals.map((signal) => {
                    const style = STATE_STYLES[signal.state] ?? STATE_STYLES.ok!;
                    return (
                      <li key={signal.key} className="flex items-baseline gap-2.5 text-sm">
                        <span className={`w-3 shrink-0 ${style.tone}`} aria-hidden>
                          {style.mark}
                        </span>
                        <span className="w-14 shrink-0 text-right font-medium tabular-nums">
                          {signal.value}
                        </span>
                        <span className="min-w-0 flex-1">
                          {signal.label}
                          <span className="ml-1.5 text-xs text-slate-400 dark:text-slate-600">
                            {signal.note}
                          </span>
                        </span>
                        <span className="sr-only">{signal.state}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>

            {nadir !== null && nadir < 92 && (
              <Card title="Worth a look">
                <p className="text-sm">
                  <span className="font-medium">{num(nadir, 0)}% blood oxygen</span> at{" "}
                  {oxygen.lowest_at ? clock(oxygen.lowest_at, timezone) : "some point"}, against a
                  night averaging {num(oxygen.mean, 0)}%.
                </p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {oxygen.minutes_under_90} minute{oxygen.minutes_under_90 === 1 ? "" : "s"} below
                  90% across {num(oxygen.hours_covered, 1)} measured hours.
                </p>
              </Card>
            )}
          </div>

          <Card
            title="Architecture"
            subtitle="What the stage totals cannot say: when sleep arrived, and how broken it was."
          >
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <Row
                label="Time to fall asleep"
                value={
                  arch.sleep_onset_minutes === null || arch.sleep_onset_minutes === undefined
                    ? null
                    : `${num(arch.sleep_onset_minutes, 0)}m`
                }
                note="normal under 30m"
              />
              <Row
                label="REM latency"
                value={
                  arch.rem_latency_minutes === null || arch.rem_latency_minutes === undefined
                    ? null
                    : `${num(arch.rem_latency_minutes, 0)}m`
                }
                note="normal 70–120m"
              />
              <Row
                label="Awake after falling asleep"
                value={
                  arch.waso_minutes === null || arch.waso_minutes === undefined
                    ? null
                    : `${num(arch.waso_minutes, 0)}m`
                }
                note={`${arch.wake_episodes} episode${arch.wake_episodes === 1 ? "" : "s"}`}
              />
              <Row
                label="Cycles observed"
                value={arch.cycles || null}
                note="REM periods; the last is usually cut short"
              />
            </dl>

            {arch.rem_periods.length > 0 && (
              <div className="mt-4">
                <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
                  REM periods. In a normal night these recur roughly every 90 minutes and get
                  longer towards morning.
                </p>
                <ol className="space-y-0.5 text-xs tabular-nums">
                  {arch.rem_periods.map((period) => (
                    <li key={period.started_at} className="flex justify-between gap-3">
                      <span className="text-slate-500 dark:text-slate-400">
                        {clock(period.started_at, timezone)} – {clock(period.ended_at, timezone)}
                      </span>
                      <span>{num(period.minutes, 0)}m</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Card>

          <Card
            title="Stage proportions"
            subtitle="As a share of time asleep, against the normal adult range."
          >
            {Object.keys(arch.stage_share ?? {}).length === 0 ? (
              <Empty>No stage data for this night.</Empty>
            ) : (
              <ul className="space-y-3">
                {(["deep", "rem", "light"] as const).map((key) => {
                  const value = arch.stage_share?.[key];
                  const range = arch.stage_reference?.[key];
                  const inRange =
                    value !== null && value !== undefined && range
                      ? value >= range[0]! && value <= range[1]!
                      : null;
                  return (
                    <li key={key}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span className="capitalize">{key}</span>
                        <span className="tabular-nums">
                          {value === null || value === undefined ? "—" : `${num(value, 1)}%`}
                          {range && (
                            <span className="ml-2 text-slate-400 dark:text-slate-600">
                              normal {range[0]}–{range[1]}%
                            </span>
                          )}
                        </span>
                      </div>
                      {/* The bar is the axis: the shaded stretch is the normal
                          range and the tick is where this night landed, so
                          "inside or outside" is one glance rather than a
                          comparison of two numbers. */}
                      <div className="relative h-2.5 w-full rounded-sm bg-slate-100 dark:bg-slate-800">
                        {range && (
                          <span
                            className="absolute inset-y-0 rounded-sm"
                            style={{
                              left: `${range[0]}%`,
                              width: `${range[1]! - range[0]!}%`,
                              backgroundColor: "var(--viz-normal-band)",
                            }}
                          />
                        )}
                        {value !== null && value !== undefined && (
                          <span
                            className="absolute inset-y-0 w-0.5"
                            style={{
                              left: `${Math.min(100, value)}%`,
                              backgroundColor:
                                inRange === false ? "var(--viz-warning)" : "var(--viz-good)",
                            }}
                          />
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            {night.context.breathing_rate !== undefined && (
              <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
                Breathing rate {num(night.context.breathing_rate, 1)}/min for the night. Fitbit
                publishes one figure per night and no minute series, so it cannot join the
                timeline above.
              </p>
            )}
          </Card>
        </div>

        {oxygen.dips.length > 0 && (
          <Card
            title="Oxygen dips"
            subtitle="Falls of 3 or more points below the preceding ten minutes, and how long each lasted."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                    <th className="pb-2 text-left font-normal">Started</th>
                    <th className="pb-2 text-right font-normal">Lasted</th>
                    <th className="pb-2 text-right font-normal">Fell by</th>
                    <th className="pb-2 text-right font-normal">Lowest</th>
                  </tr>
                </thead>
                <tbody>
                  {oxygen.dips.map((dip) => (
                    <tr
                      key={dip.started_at}
                      className="border-b border-slate-100 dark:border-slate-800/60"
                    >
                      <td className="py-1.5 tabular-nums">{clock(dip.started_at, timezone)}</td>
                      <td className="py-1.5 text-right tabular-nums">{dip.minutes}m</td>
                      <td className="py-1.5 text-right tabular-nums">−{num(dip.drop, 1)}</td>
                      <td
                        className={`py-1.5 text-right tabular-nums ${
                          dip.lowest < 90 ? "text-amber-600 dark:text-amber-400" : ""
                        }`}
                      >
                        {num(dip.lowest, 0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
              {oxygen.events_per_hour["3pct"] !== null &&
                oxygen.events_per_hour["3pct"] !== undefined && (
                  <>
                    {num(oxygen.events_per_hour["3pct"], 1)} dips per hour at 3 points,{" "}
                    {num(oxygen.events_per_hour["4pct"], 1)} at 4, over{" "}
                    {num(oxygen.hours_covered, 1)} measured hours.{" "}
                  </>
                )}
              <strong>This is not an ODI.</strong> A real oxygen desaturation index is scored from
              continuous oximetry at one reading per second; this is a wrist reflectance estimate
              averaged into one-minute buckets, and the brief dips that characterise sleep apnoea
              are exactly the ones a one-minute average smooths away. Read it as a prompt to ask
              someone, never as a result.
            </p>
          </Card>
        )}

        <p className="text-center text-xs text-slate-400 dark:text-slate-600">
          <Link href="/sleep?days=30" className="hover:underline">
            See how this night compares with the last 30 days →
          </Link>
        </p>
      </div>
    </>
  );
}

function Row({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
}) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="tabular-nums">
        {value ?? "—"}
        {note && <span className="ml-2 text-xs text-slate-400 dark:text-slate-600">{note}</span>}
      </dd>
    </div>
  );
}
