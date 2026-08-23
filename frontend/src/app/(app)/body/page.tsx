import { serverGet } from "@/lib/api/server";
import type { HealthBody } from "@/lib/api/types";

import { LineChart } from "../charts";
import { Card, Empty, LONG_RANGES, num, PageHeader, RangeTabs, shortDate, Stat } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Body: tape-measure numbers and the functional self-tests.
 *
 * The dashboard had no page for these - they only appeared bucketed on the
 * cycles view, which is the wrong place: they move over months, so what you
 * want is the series, not the seasonal average.
 *
 * **Waist-to-height, not BMI.** It is the better predictor of the thing being
 * watched here, needs no scales, and the healthy threshold is one number
 * everybody can remember: keep the waist under half your height. It is shown
 * only when a height is on the profile - guessing one would make the ratio
 * confidently wrong rather than absent.
 */

//: Waist under half of height. The whole ratio in one number.
const WAIST_HEIGHT_LIMIT = 0.5;

const MEASUREMENTS = [
  { key: "waist_cm", label: "Waist", unit: "cm" },
  { key: "hips_cm", label: "Hips", unit: "cm" },
  { key: "neck_cm", label: "Neck", unit: "cm" },
  { key: "body_fat_pct", label: "Body fat", unit: "%" },
] as const;

const TESTS = [
  { key: "grip_kg", label: "Grip strength", unit: "kg", hint: "higher is better" },
  { key: "single_leg_balance_s", label: "Single-leg balance", unit: "s", hint: "higher is better" },
  { key: "sit_to_stand_reps", label: "Sit-to-stand", unit: "reps", hint: "in 30 seconds" },
  { key: "dead_hang_s", label: "Dead hang", unit: "s", hint: "higher is better" },
] as const;

export default async function BodyPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 730;

  const body = await serverGet<HealthBody>(`/health/body?days=${days}`);

  // Oldest-first, which is what a chart plots. The API returns newest-first
  // because the tables below read better that way.
  const measurements = body.measurements.slice().reverse();
  const tests = body.tests.slice().reverse();

  const series = (rows: Array<Record<string, unknown>>, key: string) =>
    rows
      .filter((row) => row[key] !== null && row[key] !== undefined)
      .map((row) => ({ date: String(row.local_date), value: Number(row[key]) }));

  const latestMeasurement = body.measurements[0];
  const latestTest = body.tests[0];
  const ratio =
    body.height_cm && latestMeasurement?.waist_cm
      ? latestMeasurement.waist_cm / body.height_cm
      : null;

  return (
    <>
      <PageHeader
        title="Body"
        subtitle={`${body.measurements.length} measurements and ${body.tests.length} self-tests over ${days} days.`}
      >
        <RangeTabs basePath="/body" current={days} options={LONG_RANGES} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Waist"
          value={latestMeasurement?.waist_cm ? `${num(latestMeasurement.waist_cm)} cm` : null}
          sub={latestMeasurement ? shortDate(latestMeasurement.local_date) : undefined}
        />
        <Stat
          label="Waist-to-height"
          value={ratio ? num(ratio, 3) : null}
          sub={
            body.height_cm
              ? `healthy under ${WAIST_HEIGHT_LIMIT} · height ${num(body.height_cm)} cm`
              : "set a height on the profile to derive this"
          }
          tone={
            ratio === null
              ? ""
              : ratio <= WAIST_HEIGHT_LIMIT
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-amber-600 dark:text-amber-400"
          }
        />
        <Stat
          label="Body fat"
          value={
            latestMeasurement?.body_fat_pct ? `${num(latestMeasurement.body_fat_pct)}%` : null
          }
        />
        <Stat
          label="Grip strength"
          value={latestTest?.grip_kg ? `${num(latestTest.grip_kg)} kg` : null}
          sub={latestTest ? shortDate(latestTest.local_date) : undefined}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {MEASUREMENTS.map((field) => {
          const points = series(measurements, field.key);
          if (points.length === 0) return null;
          return (
            <Card key={field.key} title={field.label} subtitle={`${points.length} readings`}>
              <LineChart
                series={[{ label: field.label, points }]}
                height={180}
                unit={field.unit}
              />
            </Card>
          );
        })}

        {TESTS.map((field) => {
          const points = series(tests, field.key);
          if (points.length === 0) return null;
          return (
            <Card key={field.key} title={field.label} subtitle={field.hint}>
              <LineChart
                series={[{ label: field.label, points }]}
                height={180}
                unit={field.unit}
                zeroBased
              />
            </Card>
          );
        })}
      </div>

      {body.measurements.length === 0 && body.tests.length === 0 && (
        <Card>
          <Empty>
            Nothing measured in this window. Measurements and fitness tests arrive from the phone
            app.
          </Empty>
        </Card>
      )}

      {body.measurements.length > 0 && (
        <Card title="Measurements" className="mt-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                  <th className="pb-2 text-left font-normal">Date</th>
                  {MEASUREMENTS.map((field) => (
                    <th key={field.key} className="pb-2 text-right font-normal">
                      {field.label}
                    </th>
                  ))}
                  <th className="pb-2 text-left font-normal">Notes</th>
                </tr>
              </thead>
              <tbody>
                {body.measurements.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 dark:border-slate-800/60">
                    <td className="py-1.5">{shortDate(row.local_date)}</td>
                    {MEASUREMENTS.map((field) => (
                      <td key={field.key} className="py-1.5 text-right tabular-nums">
                        {row[field.key] === null || row[field.key] === undefined
                          ? "—"
                          : num(row[field.key])}
                      </td>
                    ))}
                    <td className="py-1.5 text-xs text-slate-500">{row.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {body.tests.length > 0 && (
        <Card title="Fitness self-tests" subtitle="Higher is better for every one of them." className="mt-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                  <th className="pb-2 text-left font-normal">Date</th>
                  {TESTS.map((field) => (
                    <th key={field.key} className="pb-2 text-right font-normal">
                      {field.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.tests.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 dark:border-slate-800/60">
                    <td className="py-1.5">{shortDate(row.local_date)}</td>
                    {TESTS.map((field) => (
                      <td key={field.key} className="py-1.5 text-right tabular-nums">
                        {row[field.key] === null || row[field.key] === undefined
                          ? "—"
                          : num(row[field.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
