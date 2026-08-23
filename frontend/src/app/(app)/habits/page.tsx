import { serverGet } from "@/lib/api/server";
import type { HealthHabitHistory } from "@/lib/api/types";

import { band, Card, Empty, num, PageHeader, RangeTabs, shortDate } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Habits: the completion grid, the streaks, and the recent rates.
 *
 * Ported from the dashboard's `habits.html`. The grid is the whole page - a
 * list of "you completed 4 of 6 today" answers a question nobody asks, whereas
 * a wall of cells shows the shape of a month at a glance: which habit is
 * carrying, which one quietly stopped three weeks ago.
 *
 * Streaks read the whole history rather than the window on screen, so a
 * 200-day run is still 200 days long when the grid shows a month of it.
 */

const RANGES = [
  { days: 30, label: "30d" },
  { days: 60, label: "60d" },
  { days: 90, label: "90d" },
  { days: 180, label: "6mo" },
] as const;

export default async function HabitsPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 30;

  const history = await serverGet<HealthHabitHistory>(`/health/habits?days=${days}`);
  const { dates, habits } = history;

  // Days worth marking on the axis. Every date is unreadable past a fortnight.
  const labelEvery = Math.ceil(dates.length / 10);

  return (
    <>
      <PageHeader
        title="Habits"
        subtitle={`${habits.length} habits over ${dates.length} days, to ${history.end}.`}
      >
        <RangeTabs basePath="/habits" current={days} options={RANGES} />
      </PageHeader>

      {habits.length === 0 ? (
        <Card>
          <Empty>No habits defined yet. They arrive from the phone app.</Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card title="Completion grid" subtitle="Newest on the right. Hover a cell for its date.">
            <div className="overflow-x-auto">
              <table className="border-separate border-spacing-0 text-sm">
                <caption className="sr-only">
                  Habit completions from {history.start} to {history.end}
                </caption>
                <thead>
                  <tr>
                    <th className="sticky left-0 z-10 bg-white pr-3 text-left text-xs font-normal text-slate-500 dark:bg-slate-900">
                      Habit
                    </th>
                    {dates.map((date, index) => (
                      <th
                        key={date}
                        scope="col"
                        className="px-px pb-1 text-[9px] font-normal text-slate-400 dark:text-slate-600"
                      >
                        {/* Sparse labels: a date over every cell is a smear. */}
                        <span className={index % labelEvery === 0 ? "" : "sr-only"}>
                          {index % labelEvery === 0 ? shortDate(date) : date}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {habits.map((habit) => (
                    <tr key={habit.id}>
                      <th
                        scope="row"
                        className="sticky left-0 z-10 whitespace-nowrap bg-white pr-3 text-left text-xs font-normal dark:bg-slate-900"
                      >
                        {habit.name}
                      </th>
                      {habit.completed.map((done, index) => (
                        <td key={dates[index]} className="p-px">
                          {/* A 2px gap between cells rather than a border - the
                              gap is what separates marks, never a stroke. */}
                          <div
                            className={`size-3 rounded-[2px] ${
                              done
                                ? "bg-emerald-500 dark:bg-emerald-500"
                                : "bg-slate-100 dark:bg-slate-800"
                            }`}
                            title={`${habit.name} — ${dates[index]}: ${done ? "done" : "not done"}`}
                          />
                          <span className="sr-only">{done ? "done" : "not done"}</span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card
            title="Streaks and rates"
            subtitle="Streaks span the whole history, not just the window above."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                    <th className="pb-2 text-left font-normal">Habit</th>
                    <th className="pb-2 text-right font-normal">Current</th>
                    <th className="pb-2 text-right font-normal">Best</th>
                    <th className="pb-2 text-right font-normal">7 days</th>
                    <th className="pb-2 text-right font-normal">30 days</th>
                    <th className="pb-2 text-right font-normal">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {habits.map((habit) => (
                    <tr key={habit.id} className="border-b border-slate-100 dark:border-slate-800/60">
                      <td className="py-1.5">{habit.name}</td>
                      <td className="py-1.5 text-right tabular-nums">
                        {habit.current_streak > 0 ? `${habit.current_streak}d` : "—"}
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-slate-500">
                        {habit.best_streak > 0 ? `${habit.best_streak}d` : "—"}
                      </td>
                      <td className={`py-1.5 text-right tabular-nums ${band(habit.rate_7, 80, 50)}`}>
                        {num(habit.rate_7, 0)}%
                      </td>
                      <td className={`py-1.5 text-right tabular-nums ${band(habit.rate_30, 80, 50)}`}>
                        {num(habit.rate_30, 0)}%
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-slate-500">
                        {habit.total}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
