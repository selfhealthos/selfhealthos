import { serverGet } from "@/lib/api/server";
import type { HealthGymLog } from "@/lib/api/types";

import { BarChart } from "../charts";
import { Card, DEFAULT_RANGES, Empty, num, PageHeader, RangeTabs, shortDate, Stat } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Gym: tonnage over time, and the per-exercise grid behind it.
 *
 * Tonnage - weight x reps, summed - is the one number that answers "am I
 * doing more work than I was", which neither a set count nor a top weight
 * can. A week of heavy triples and a week of light volume look identical by
 * session count and opposite by tonnage.
 *
 * The grid underneath is exercises down, dates across, newest date first.
 * Reading a single movement's working weight backwards through time is the
 * question this page exists for, and that wants one row per exercise with the
 * dates beside each other rather than a card per day.
 *
 * Rest days appear nowhere - see `services.gym_log`. A day off is absent, not
 * a zero, and padding the gaps would both flatten the chart and imply
 * sessions that never happened.
 */

export default async function GymPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 30;

  const log = await serverGet<HealthGymLog>(`/health/gym?days=${days}`);

  const bars = log.series.map((point) => ({
    label: shortDate(point.date),
    value: point.tonnage_kg,
    title: `${shortDate(point.date)} — ${num(point.tonnage_kg, 0)} kg`,
  }));

  //: Mean over sessions, not over calendar days: dividing a month's tonnage
  //: by 30 answers a question nobody asked, since the rest days were never
  //: training days.
  const perSession = log.sessions > 0 ? log.total_kg / log.sessions : 0;

  return (
    <>
      <PageHeader
        title="Gym"
        subtitle={`Tonnage and working weights over the last ${log.days} days.`}
      >
        <RangeTabs basePath="/gym" current={days} options={DEFAULT_RANGES} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Total tonnage" value={`${num(log.total_kg, 0)} kg`} />
        <Stat label="Sessions" value={String(log.sessions)} />
        <Stat label="Per session" value={`${num(perSession, 0)} kg`} />
      </div>

      <Card title="Tonnage per session" subtitle="Weight x reps, summed across every set that day.">
        <BarChart bars={bars} unit=" kg" colour="var(--color-brand-purple)" height={220} />
      </Card>

      <div className="mt-4">
        <Card
          title="Working weights by exercise"
          subtitle="Newest session first. Each cell is that day's tonnage, with the sets beneath."
        >
          {log.exercises.length === 0 ? (
            <Empty>No gym sets logged in this window.</Empty>
          ) : (
            //: The grid grows a column per session, so it scrolls inside its
            //: own box rather than pushing the page sideways.
            <div className="-mx-1 overflow-x-auto px-1">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th className="sticky left-0 z-10 border-b border-border bg-surface py-2 pr-3 text-left text-xs font-semibold tracking-wide text-ink-dim uppercase">
                      Exercise
                    </th>
                    {log.dates.map((day) => (
                      <th
                        key={day}
                        className="border-b border-border px-3 py-2 text-right text-xs font-semibold whitespace-nowrap text-ink-dim"
                      >
                        {shortDate(day)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {log.exercises.map((exercise) => (
                    <tr key={exercise.name} className="align-top">
                      <th
                        scope="row"
                        className="sticky left-0 z-10 border-b border-border bg-surface py-2 pr-3 text-left font-medium whitespace-nowrap text-ink"
                      >
                        {exercise.name}
                      </th>
                      {exercise.cells.map((cell, i) => (
                        <td
                          key={log.dates[i]}
                          className="border-b border-border px-3 py-2 text-right whitespace-nowrap tabular-nums"
                        >
                          {cell.sets.length === 0 ? (
                            <span className="text-ink-muted">—</span>
                          ) : (
                            <>
                              {/* Bodyweight work carries no external load, so
                                  its tonnage really is 0. Printing "0 kg" over
                                  a set of chin-ups reads as a failed entry, so
                                  the headline is dropped and the sets speak. */}
                              {cell.tonnage_kg ? (
                                <div className="font-medium text-ink">
                                  {num(cell.tonnage_kg, 0)} kg
                                </div>
                              ) : null}
                              <div className="text-xs text-ink-dim">{cell.sets.join(" ")}</div>
                            </>
                          )}
                        </td>
                      ))}
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
