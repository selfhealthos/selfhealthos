import { serverGet } from "@/lib/api/server";
import type { HealthFitness } from "@/lib/api/types";

import { LineChart } from "../charts";
import { Card, Empty, LONG_RANGES, num, PageHeader, RangeTabs, shortDate, Stat } from "../ui";

export const dynamic = "force-dynamic";

/**
 * The functional self-tests: what the body can still do, rather than what it
 * measures.
 *
 * Split off the Body page when that became the composition page. Grip strength
 * is not a tape-measure number, and the two subjects under one title meant the
 * charts you wanted were always below the charts you did not.
 *
 * **Deliberately unbanded.** Higher is better for every one of them and that
 * is the whole of the published guidance worth applying: there is no
 * literature threshold for a dead hang, and grip norms vary by age, sex, hand
 * and dynamometer by more than the difference this page is for. So these are
 * lines against your own history, and the only comparison offered is with
 * yourself. `scoring.py`'s rule, unchanged: an uncoloured number says "no
 * opinion", a guessed colour says something false with total confidence.
 */

const TESTS = [
  { key: "grip_kg", label: "Grip strength", unit: "kg", hint: "higher is better" },
  { key: "single_leg_balance_s", label: "Single-leg balance", unit: "s", hint: "eyes open, one leg" },
  { key: "sit_to_stand_reps", label: "Sit-to-stand", unit: "reps", hint: "in 30 seconds" },
  { key: "dead_hang_s", label: "Dead hang", unit: "s", hint: "higher is better" },
] as const;

export default async function FitnessPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 730;

  const data = await serverGet<HealthFitness>(`/health/fitness?days=${days}`);
  // Oldest-first for the charts; the API returns newest-first for the table.
  const tests = data.tests.slice().reverse();
  const latest = data.tests[0];

  const series = (key: string) =>
    tests
      .filter((row) => row[key as keyof typeof row] !== null && row[key as keyof typeof row] !== undefined)
      .map((row) => ({
        date: row.local_date,
        value: Number(row[key as keyof typeof row]),
      }));

  return (
    <>
      <PageHeader
        title="Fitness tests"
        subtitle={`${data.tests.length} self-tests over ${days} days. Higher is better for every one of them.`}
      >
        <RangeTabs basePath="/fitness" current={days} options={LONG_RANGES} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {TESTS.map((test) => {
          const value = latest?.[test.key];
          return (
            <Stat
              key={test.key}
              label={test.label}
              value={
                value === null || value === undefined ? null : `${num(value)} ${test.unit}`
              }
              sub={latest ? shortDate(latest.local_date) : undefined}
            />
          );
        })}
      </div>

      {data.tests.length === 0 ? (
        <Card>
          <Empty>
            No self-tests in this window. They arrive from the phone app, which is where they are
            timed.
          </Empty>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {TESTS.map((test) => {
              const points = series(test.key);
              if (points.length === 0) return null;
              return (
                <Card key={test.key} title={test.label} subtitle={test.hint}>
                  {/* Zero-based: these are counts and durations, where the
                      distance from nothing is the point. A dead hang plotted
                      from 40s to 45s makes a 5-second gain look like a
                      transformation. */}
                  <LineChart
                    series={[{ label: test.label, points }]}
                    height={180}
                    unit={test.unit}
                    zeroBased
                  />
                </Card>
              );
            })}
          </div>

          <Card title="Self-tests" subtitle="Newest first." className="mt-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-ink-dim">
                    <th className="pb-2 text-left font-normal">Date</th>
                    {TESTS.map((test) => (
                      <th key={test.key} className="pb-2 text-right font-normal">
                        {test.label}
                        <span className="ml-1 text-ink-muted">{test.unit}</span>
                      </th>
                    ))}
                    <th className="pb-2 text-left font-normal">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tests.map((row) => (
                    <tr key={row.id} className="border-b border-border/60">
                      <td className="py-1.5">{shortDate(row.local_date)}</td>
                      {TESTS.map((test) => (
                        <td key={test.key} className="py-1.5 text-right tabular-nums">
                          {num(row[test.key])}
                        </td>
                      ))}
                      <td className="py-1.5 text-xs text-ink-dim">{row.notes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </>
  );
}
