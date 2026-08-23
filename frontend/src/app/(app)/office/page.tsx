import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthOffice } from "@/lib/api/types";

import { CalendarHeatmap } from "../charts";
import { Card, Empty, PageHeader, shortDate, Stat } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Office days: a calendar of the days worked in the office.
 *
 * **The source file is named `wfh.ndjson` and lists the opposite of what its
 * name says.** Reading it backwards has already inverted an analysis once, so
 * the model is called `OfficeDay` and so is this page — the mistake is not
 * representable here, only upstream in the importer where it is commented.
 *
 * The other thing that has to be said out loud is that **absence means
 * unknown**. Outside the range the record covers, a blank square is "no data",
 * not "worked from home" — so the page states its coverage rather than drawing
 * a confident empty January.
 */

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export default async function OfficePage({
  searchParams,
}: {
  searchParams: Promise<{ year?: string }>;
}) {
  const { year: raw } = await searchParams;
  const requested = Number(raw);
  const office = await serverGet<HealthOffice>(
    `/health/office${Number.isFinite(requested) && requested > 0 ? `?year=${requested}` : ""}`,
  );

  const coversFrom = office.covers_from ?? null;
  const coversTo = office.covers_to ?? null;

  // The heatmap wants a value per day; an office day is 1 and every other day
  // inside the covered range is 0. Days outside coverage are left absent, so
  // they render as "no data" rather than as a day spent at home.
  const values: Record<string, number> = {};
  const yearStart = `${office.year}-01-01`;
  const yearEnd = `${office.year}-12-31`;
  if (coversFrom && coversTo) {
    const from = coversFrom > yearStart ? coversFrom : yearStart;
    const to = coversTo < yearEnd ? coversTo : yearEnd;
    const cursor = new Date(`${from}T00:00:00Z`);
    const stop = new Date(`${to}T00:00:00Z`);
    while (cursor <= stop) {
      values[cursor.toISOString().slice(0, 10)] = 0;
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
  }
  for (const day of office.days) values[day] = 1;

  const busiest = office.by_month.reduce(
    (best, month) => (month.count > best.count ? month : best),
    office.by_month[0] ?? { month: 1, count: 0 },
  );

  return (
    <>
      <PageHeader title="Office days" subtitle={`Days worked in the office during ${office.year}.`}>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Year">
          {office.years.map((year) => (
            <Link
              key={year}
              href={`/office?year=${year}`}
              aria-current={year === office.year ? "true" : undefined}
              className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                year === office.year
                  ? "bg-slate-900 font-medium text-white dark:bg-slate-100 dark:text-slate-900"
                  : "border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800"
              }`}
            >
              {year}
            </Link>
          ))}
        </div>
      </PageHeader>

      {coversFrom === null || coversTo === null ? (
        <Card>
          <Empty>No office days recorded. They arrive from the phone app&apos;s calendar.</Empty>
        </Card>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label={`Days in ${office.year}`} value={office.total.toLocaleString()} />
            <Stat
              label="Per week"
              value={(office.total / 52).toFixed(1)}
              sub="averaged over the whole year"
            />
            <Stat
              label="Busiest month"
              value={busiest.count > 0 ? MONTHS[busiest.month - 1] : null}
              sub={busiest.count > 0 ? `${busiest.count} days` : undefined}
            />
            <Stat
              label="Record covers"
              value={`${shortDate(coversFrom)} –`}
              sub={`${shortDate(coversTo)}. Outside this, nothing is known.`}
            />
          </div>

          <div className="space-y-4">
            <Card
              title="Calendar"
              subtitle="One column per week. An empty square inside the covered range is a day not in the office; outside it, a day with no record at all."
            >
              <CalendarHeatmap
                values={values}
                start={`${office.year}-01-01`}
                end={`${office.year}-12-31`}
                unit=""
                emptyLabel="outside the recorded range"
              />
            </Card>

            <Card title="By month">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                    <th className="pb-2 text-left font-normal">Month</th>
                    <th className="pb-2 text-right font-normal">Days in the office</th>
                    <th className="pb-2 pl-4 text-left font-normal">&nbsp;</th>
                  </tr>
                </thead>
                <tbody>
                  {office.by_month.map((month) => (
                    <tr key={month.month} className="border-b border-slate-100 dark:border-slate-800/60">
                      <td className="py-1.5">{MONTHS[month.month - 1]}</td>
                      <td className="py-1.5 text-right tabular-nums">{month.count}</td>
                      <td className="w-1/2 py-1.5 pl-4">
                        <div
                          aria-hidden
                          className="h-2 rounded-full"
                          style={{
                            width: `${(month.count / Math.max(busiest.count, 1)) * 100}%`,
                            backgroundColor: "var(--viz-1)",
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
