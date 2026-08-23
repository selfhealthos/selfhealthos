import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthHeartDay, HealthHeartHistory } from "@/lib/api/types";

import { Card, Empty, num, PageHeader, shortDate, Stat } from "../ui";
import { HeartDayChart, ZoneLegend } from "./HeartDayChart";
import { HeartTabs, WINDOWS } from "./HeartTabs";
import { HeartTrendChart, TrendLegend } from "./HeartTrendChart";

export const dynamic = "force-dynamic";

/**
 * Heart, at whichever resolution the question needs.
 *
 * One master chart that changes with the window rather than four charts of
 * equal weight, which is what this page used to be: HRV, resting heart rate,
 * an intraday trace and a zone breakdown, none of them dominant and none of
 * them large enough to read. The two questions people actually bring here are
 * "what did today do to me" and "am I recovering", and they want different
 * pictures - so the tab picks the picture.
 *
 * Underneath, the same scored table the sleep page uses, against the same
 * thresholds in `scoring.py`.
 */

const TIME_ZONE = "Australia/Melbourne";

//: Colours from the categorical slots, fixed per series so a line means the
//: same thing between windows.
const SERIES_COLOURS: Record<string, string> = {
  hrv_rmssd: "var(--viz-3)",
  resting_hr: "var(--viz-8)",
};

export default async function HeartPage({
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
  const day = await serverGet<HealthHeartDay>(
    date ? `/health/heart/days/${date}` : "/health/heart/latest",
  );
  // For the day picker beneath the chart. Cheap, and it is the only way to
  // know which neighbouring days are worth offering.
  const history = await serverGet<HealthHeartHistory>("/health/heart?days=14");

  const asleepMinutes = day.sleep.reduce(
    (total, window) =>
      total + (new Date(window.ended_at).getTime() - new Date(window.started_at).getTime()) / 60_000,
    0,
  );

  return (
    <>
      <PageHeader
        title="Heart"
        subtitle={
          day.count === 0
            ? `No minute-level heart rate recorded on ${shortDate(day.date)}.`
            : `Every minute of ${shortDate(day.date)} — ${day.count.toLocaleString()} readings.`
        }
      >
        <HeartTabs current={1} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Resting"
          value={day.resting_hr ? `${num(day.resting_hr, 0)} bpm` : null}
          sub="the day's floor"
        />
        <Stat
          label="Lowest"
          value={day.minimum ? `${num(day.minimum, 0)} bpm` : null}
          sub={asleepMinutes > 0 ? "usually mid-sleep" : "across the day"}
        />
        <Stat
          label="Peak"
          value={day.maximum ? `${num(day.maximum, 0)} bpm` : null}
          sub="highest minute"
        />
        <Stat
          label="Vigorous"
          value={vigorousLabel(day)}
          sub="cardio and peak zones"
        />
      </div>

      <div className="space-y-4">
        <Card
          title={`Through ${shortDate(day.date)}`}
          subtitle="The bands are the device's own heart-rate zones, so the shading and the minute totals come from the same reading. The grey stretches are time asleep."
        >
          <ZoneLegend zones={day.zones} asleep={day.sleep.length > 0} />
          <HeartDayChart
            start={day.start}
            end={day.end}
            timeZone={TIME_ZONE}
            points={day.points}
            zones={day.zones}
            sleep={day.sleep}
            restingHr={day.resting_hr ?? null}
          />
          {day.count === 0 && (
            <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
              No minute samples for this day. Intraday data needs a connected Fitbit with a Personal
              app registration, and the sync fetches it only for days that have none — so a day it
              skipped stays empty until the next sync covers it.
            </p>
          )}
        </Card>

        <Card title="Other days" subtitle="Days with a recorded resting heart rate, newest first.">
          <div className="flex flex-wrap gap-2 text-xs">
            {history.rows.slice(0, 14).map((row) => (
              <Link
                key={row.date}
                href={`/heart?days=1&date=${row.date}`}
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

function vigorousLabel(day: HealthHeartDay): string | null {
  const minutes = day.zones
    .filter((zone) => zone.key === "cardio" || zone.key === "peak")
    .reduce<number | null>(
      (total, zone) => (zone.minutes == null ? total : (total ?? 0) + zone.minutes),
      null,
    );
  return minutes === null ? null : `${Math.round(minutes)} min`;
}

/* -------------------------------------------------------------------------
 * A window of days
 * ---------------------------------------------------------------------- */

async function WindowView({ days }: { days: number }) {
  const history = await serverGet<HealthHeartHistory>(`/health/heart?days=${days}`);
  const series = history.series.map((one) => ({
    ...one,
    colour: SERIES_COLOURS[one.metric] ?? "var(--viz-1)",
  }));

  const hrv = series.find((one) => one.metric === "hrv_rmssd");
  const resting = series.find((one) => one.metric === "resting_hr");
  const latest = (metric: typeof hrv) => metric?.points[metric.points.length - 1]?.value ?? null;

  return (
    <>
      <PageHeader
        title="Heart"
        subtitle={
          history.rows.length === 0
            ? `Nothing recorded in the last ${days} days.`
            : `${history.rows.length} days with a reading, out of ${days}. Both signals are read against your own recent history, not a population range.`
        }
      >
        <HeartTabs current={days} />
      </PageHeader>

      {history.rows.length === 0 ? (
        <Card>
          <Empty>Nothing recorded in this window. Sync the watch, or widen the range.</Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card
            title="Recovery, against your own baseline"
            subtitle="HRV and resting heart rate share one scale because both live inside 0–100 in their own units. Each band is that signal's usual range over the last 30 days."
          >
            <TrendLegend series={series} />
            <HeartTrendChart series={series} start={history.start} end={history.end} />
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              The two want opposite directions — HRV up is recovery, resting heart rate up is load
              or illness — so their crossing is not an event in itself. What is worth reading is
              each line against its own band: several days of HRV below and resting heart rate
              above is the pattern that precedes most people noticing they are unwell.
            </p>
          </Card>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Baseline label="HRV (RMSSD)" unit="ms" latest={latest(hrv)} series={hrv} />
            <Baseline
              label="Resting heart rate"
              unit="bpm"
              latest={latest(resting)}
              series={resting}
            />
            <ZoneMix rows={history.rows} columns={history.columns} />
          </div>

          <Card
            title="Every day in the window"
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
                        <Link href={`/day/${row.date}`} className="hover:underline">
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
                Lowest and Peak HR are shown uncoloured on purpose: a single minute of the day
                means nothing without knowing what you were doing at the time, and resting HR is
                already the steadier version of the same signal.
              </li>
            </ol>
          </Card>
        </div>
      )}
    </>
  );
}

/** One signal's latest reading, stated against its own band rather than a range. */
function Baseline({
  label,
  unit,
  latest,
  series,
}: {
  label: string;
  unit: string;
  latest: number | null;
  series: Pick<HealthHeartHistory["series"][number], "baseline" | "direction"> | undefined;
}) {
  const baseline = series?.baseline ?? null;
  const detail = (() => {
    if (!baseline) return "not enough days for a baseline yet";
    const range = `usual ${Math.round(baseline.low)}–${Math.round(baseline.high)} ${unit}`;
    if (latest === null) return range;
    if (latest > baseline.high) return `above ${range}`;
    if (latest < baseline.low) return `below ${range}`;
    return `within ${range}`;
  })();

  // Tone follows the series' own direction, which is why the API sends it:
  // "above usual" is good news for HRV and bad news for resting heart rate.
  const good = series?.direction === "up";
  const tone =
    !baseline || latest === null
      ? ""
      : latest > baseline.high
        ? good
          ? "text-emerald-600 dark:text-emerald-400"
          : "text-amber-600 dark:text-amber-400"
        : latest < baseline.low
          ? good
            ? "text-amber-600 dark:text-amber-400"
            : "text-emerald-600 dark:text-emerald-400"
          : "";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="mb-1 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-500">
        {label}
      </p>
      <p className={`text-2xl font-bold ${tone}`}>
        {latest === null ? "—" : `${Math.round(latest)} ${unit}`}
      </p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p>
    </div>
  );
}

/**
 * Vigorous minutes, stated as a weekly rate.
 *
 * A rate rather than a total, because the recommendation is weekly and the
 * window is not: 90 minutes is excellent over seven days and poor over ninety.
 * Averaged over the days that actually have zone minutes, for the same reason
 * the sleep page averages over recorded nights - dividing by the window would
 * mostly measure the days nobody wore the watch.
 */
function ZoneMix({
  rows,
  columns,
}: {
  rows: HealthHeartHistory["rows"];
  columns: HealthHeartHistory["columns"];
}) {
  const index = columns.findIndex((column) => column.key === "vigorous_minutes");
  const values = rows
    .map((row) => (index >= 0 ? row.cells[index]?.value : null))
    .filter((value): value is number => value !== null && value !== undefined);
  const total = values.reduce((sum, value) => sum + value, 0);
  const perWeek = values.length === 0 ? null : (total / values.length) * 7;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="mb-1 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-500">
        Vigorous minutes
      </p>
      <p
        className={`text-2xl font-bold ${
          perWeek !== null && perWeek < 75 ? "text-amber-600 dark:text-amber-400" : ""
        }`}
      >
        {perWeek === null ? "—" : `${Math.round(perWeek)}/wk`}
      </p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        {perWeek === null
          ? "no zone minutes recorded"
          : `cardio and peak, over ${values.length} day${values.length === 1 ? "" : "s"} — WHO asks 75–150`}
      </p>
    </div>
  );
}
