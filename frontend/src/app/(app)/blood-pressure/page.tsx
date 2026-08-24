import { serverGet } from "@/lib/api/server";
import type { HealthTrend } from "@/lib/api/types";

import { LineChart } from "../charts";
import { band, Card, LONG_RANGES, num, PageHeader, RangeTabs, shortDate, Stat } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Blood pressure: the one number here with a published target.
 *
 * Ported from the dashboard's `bp_weight.html`, which is where the name
 * "BP + Weight" came from. Weight has since moved to `/body`, where it sits
 * beside the height that makes it interpretable — putting kilograms and
 * millimetres of mercury on one page was an accident of the source template,
 * and putting them on one chart with two axes would have been the classic
 * misleading chart, where the point the lines cross is pure coincidence of
 * scaling.
 *
 * Systolic and diastolic *do* share a chart, because they are one reading
 * taken together and their scales genuinely overlap.
 *
 * The reference lines are the clinical thresholds (120/80), not this person's
 * average. A target you are already meeting is not a target.
 */

const SYSTOLIC_TARGET = 120;
const DIASTOLIC_TARGET = 80;

export default async function BloodPressurePage({
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

  const trends = await serverGet<HealthTrend[]>(
    `/health/trends?metrics=systolic,diastolic&start=${iso(start)}&end=${iso(end)}&window=7`,
  );
  const byMetric = new Map(trends.map((t) => [t.metric, t]));
  const systolic = byMetric.get("systolic");
  const diastolic = byMetric.get("diastolic");

  const latest = <T,>(points: T[]): T | undefined => points[points.length - 1];
  const lastSys = latest(systolic?.points ?? []);
  const lastDia = latest(diastolic?.points ?? []);

  // Paired readings, newest first, for the table under the charts.
  const diaByDate = new Map((diastolic?.points ?? []).map((p) => [p.date, p.value]));
  const readings = (systolic?.points ?? [])
    .map((p) => ({ date: p.date, systolic: p.value, diastolic: diaByDate.get(p.date) }))
    .reverse();

  return (
    <>
      <PageHeader
        title="Blood pressure"
        subtitle={`Systolic and diastolic over ${days} days, against the clinical thresholds.`}
      >
        <RangeTabs basePath="/blood-pressure" current={days} options={LONG_RANGES} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Latest BP"
          value={
            lastSys && lastDia
              ? `${Math.round(lastSys.value)}/${Math.round(lastDia.value)}`
              : null
          }
          sub={lastSys ? `mmHg · ${shortDate(lastSys.date)}` : undefined}
          tone={band(lastSys?.value, SYSTOLIC_TARGET, 130, false)}
        />
        <Stat
          label="Average BP"
          value={
            systolic?.mean && diastolic?.mean
              ? `${Math.round(systolic.mean)}/${Math.round(diastolic.mean)}`
              : null
          }
          sub={`mmHg over ${days} days`}
        />
        <Stat
          label="Readings"
          value={readings.length || null}
          sub={`in the last ${days} days`}
        />
        <Stat
          label="Average pulse pressure"
          value={
            systolic?.mean && diastolic?.mean
              ? Math.round(systolic.mean - diastolic.mean)
              : null
          }
          sub="mmHg · systolic minus diastolic"
        />
      </div>

      <div className="space-y-4">
        <Card
          title="Blood pressure"
          subtitle="Normal is under 120/80. Elevated 120–129; high from 130/80."
        >
          <LineChart
            series={[
              {
                label: "Systolic",
                points: (systolic?.points ?? []).map((p) => ({ date: p.date, value: p.value })),
              },
              {
                label: "Diastolic",
                points: (diastolic?.points ?? []).map((p) => ({ date: p.date, value: p.value })),
              },
            ]}
            height={220}
            unit="mmHg"
            reference={{ value: SYSTOLIC_TARGET, label: "120" }}
          />
        </Card>

        <Card title="Readings" subtitle="Newest first.">
          {readings.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-600">
              No blood-pressure readings in this window.
            </p>
          ) : (
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white dark:bg-slate-900">
                  <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                    <th className="pb-2 text-left font-normal">Date</th>
                    <th className="pb-2 text-right font-normal">Systolic</th>
                    <th className="pb-2 text-right font-normal">Diastolic</th>
                    <th className="pb-2 text-right font-normal">Pulse pressure</th>
                  </tr>
                </thead>
                <tbody>
                  {readings.map((row) => (
                    <tr key={row.date} className="border-b border-slate-100 dark:border-slate-800/60">
                      <td className="py-1.5">{shortDate(row.date)}</td>
                      <td className={`py-1.5 text-right tabular-nums ${band(row.systolic, SYSTOLIC_TARGET, 130, false)}`}>
                        {Math.round(row.systolic)}
                      </td>
                      <td className={`py-1.5 text-right tabular-nums ${band(row.diastolic, DIASTOLIC_TARGET, 90, false)}`}>
                        {row.diastolic === undefined ? "—" : Math.round(row.diastolic)}
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-slate-500">
                        {row.diastolic === undefined
                          ? "—"
                          : Math.round(row.systolic - row.diastolic)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
