import { serverGet } from "@/lib/api/server";
import type { HealthGut, HealthTrend } from "@/lib/api/types";

import { BarChart, LineChart } from "../charts";
import { Card, clock, Empty, num, PageHeader, RangeTabs, shortDate, Stat } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Gut: Bristol scores over time, and what was eaten before the bad days.
 *
 * Ported from the dashboard's `gut.html`, with the correlation table rebuilt.
 * The dashboard listed every food eaten on a bad day, which reliably indicted
 * breakfast: the food eaten most often is the food most often eaten before
 * anything. The table here carries the denominator beside the count, so
 * "chocolate, 2 of 2 days" and "porridge, 2 of 60 days" stop looking alike.
 *
 * It is still a frequency count and the page says so. Two months of one
 * person's meals cannot establish a cause, and presenting it as though it
 * could is how someone ends up cutting out the wrong food for a year.
 */

const BRISTOL_MEANING: Record<number, string> = {
  1: "Separate hard lumps — constipation",
  2: "Lumpy and sausage-like — constipation",
  3: "Sausage with cracks — ideal",
  4: "Smooth and soft — ideal",
  5: "Soft blobs — lacking fibre",
  6: "Mushy — loose",
  7: "Liquid — diarrhoea",
};

function bristolTone(score: number): string {
  if (score >= 6) return "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300";
  if (score <= 2) return "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300";
  return "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
}

export default async function GutPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 30;

  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  const iso = (at: Date) => at.toISOString().slice(0, 10);

  const [detail, trends] = await Promise.all([
    serverGet<HealthGut>(`/health/gut?days=${days}`),
    serverGet<HealthTrend[]>(
      `/health/trends?metrics=bristol_mean,bm_count&start=${iso(start)}&end=${iso(end)}&window=7`,
    ),
  ]);

  const bristol = trends.find((t) => t.metric === "bristol_mean");
  const count = trends.find((t) => t.metric === "bm_count");
  const timeZone = "Australia/Melbourne";
  const total = detail.entries.length;

  return (
    <>
      <PageHeader
        title="Gut"
        subtitle={`${total} observations over ${days} days, to ${detail.end}.`}
      >
        <RangeTabs
          basePath="/gut"
          current={days}
          options={[
            { days: 30, label: "30d" },
            { days: 90, label: "90d" },
            { days: 365, label: "1y" },
          ]}
        />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Observations" value={total.toLocaleString()} />
        <Stat
          label="Mean Bristol"
          value={num(bristol?.mean)}
          sub="3–4 is ideal"
          tone={
            (bristol?.mean ?? 4) >= 5.5 || (bristol?.mean ?? 4) <= 2.5
              ? "text-amber-600 dark:text-amber-400"
              : ""
          }
        />
        <Stat
          label="Loose days"
          value={detail.bad_day_count.toLocaleString()}
          sub="a Bristol 6 or 7"
          tone={detail.bad_day_count > 0 ? "text-rose-600 dark:text-rose-400" : ""}
        />
        <Stat label="Per day" value={num(count?.mean)} sub="bowel movements" />
      </div>

      <div className="space-y-4">
        <Card title="Bristol score over time" subtitle="Daily mean, with a 7-day average.">
          <LineChart
            series={[
              {
                label: "Bristol (daily mean)",
                points: (bristol?.points ?? []).map((p) => ({ date: p.date, value: p.value })),
              },
            ]}
            height={190}
            unit="1–7"
          />
        </Card>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card title="Distribution" subtitle="Where the observations sit on the scale.">
            <BarChart
              bars={detail.distribution.map((row) => ({
                label: String(row.bristol),
                value: row.count,
                title: `Bristol ${row.bristol} — ${row.count} of ${total}: ${BRISTOL_MEANING[row.bristol]}`,
              }))}
              height={170}
              unit="observations"
              colour="var(--viz-2)"
            />
            <dl className="mt-3 space-y-1 text-xs text-slate-500 dark:text-slate-400">
              {detail.distribution
                .filter((row) => row.count > 0)
                .map((row) => (
                  <div key={row.bristol} className="flex justify-between gap-3">
                    <dt>
                      <span className={`mr-2 rounded px-1.5 py-0.5 font-mono ${bristolTone(row.bristol)}`}>
                        {row.bristol}
                      </span>
                      {BRISTOL_MEANING[row.bristol]}
                    </dt>
                    <dd className="tabular-nums">{row.count}</dd>
                  </div>
                ))}
            </dl>
          </Card>

          <Card
            title="Before the loose days"
            subtitle="A frequency count, not a cause — read both columns together."
          >
            {detail.suspects.length === 0 ? (
              <Empty>
                {detail.bad_day_count === 0
                  ? "No loose days in this window."
                  : "Not enough repeats to count anything."}
              </Empty>
            ) : (
              <>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                      <th className="pb-2 text-left font-normal">Food</th>
                      <th className="pb-2 text-right font-normal">Before a loose day</th>
                      <th className="pb-2 text-right font-normal">Days eaten</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.suspects.map((row) => (
                      <tr key={row.name} className="border-b border-slate-100 dark:border-slate-800/60">
                        <td className="py-1.5">{row.name}</td>
                        <td className="py-1.5 text-right tabular-nums">{row.before_bad_days}</td>
                        <td className="py-1.5 text-right tabular-nums text-slate-500">
                          {row.days_eaten}
                          <span className="ml-2 text-xs text-slate-400">{num(row.share, 0)}%</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 text-xs text-slate-400 dark:text-slate-600">
                  “Before” means the day itself or the day before. A food eaten every day appears
                  before everything — the second column is what tells them apart.
                </p>
              </>
            )}
          </Card>
        </div>

        <Card title="Loose days in detail" subtitle="Everything eaten that day and the day before.">
          {detail.bad_days.length === 0 ? (
            <Empty>No Bristol 6 or 7 in this window.</Empty>
          ) : (
            <ul className="space-y-3">
              {detail.bad_days
                .slice()
                .reverse()
                .map((day) => (
                  <li key={day.date} className="border-b border-slate-100 pb-3 last:border-0 dark:border-slate-800/60">
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-medium">{shortDate(day.date)}</span>
                      <span className={`rounded px-1.5 py-0.5 font-mono text-xs ${bristolTone(day.worst)}`}>
                        worst {day.worst}
                      </span>
                      <span className="text-xs text-slate-400">mean {num(day.mean)}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {day.foods.length > 0 ? day.foods.join(" · ") : "Nothing logged."}
                    </p>
                  </li>
                ))}
            </ul>
          )}
        </Card>

        <Card title="Every observation">
          {detail.entries.length === 0 ? (
            <Empty>Nothing recorded in this window.</Empty>
          ) : (
            <ol className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {detail.entries.map((entry) => (
                <li key={entry.id} className="flex items-baseline gap-3 py-1.5 text-sm">
                  <span className="w-20 shrink-0 text-xs tabular-nums text-slate-400">
                    {shortDate(entry.local_date)}
                  </span>
                  <span className="w-10 shrink-0 text-xs tabular-nums text-slate-400">
                    {clock(entry.at, timeZone)}
                  </span>
                  <span className={`rounded px-1.5 py-0.5 font-mono text-xs ${bristolTone(entry.bristol)}`}>
                    {entry.bristol}
                  </span>
                  {entry.notes && (
                    <span className="text-xs text-slate-500 dark:text-slate-400">{entry.notes}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </>
  );
}
