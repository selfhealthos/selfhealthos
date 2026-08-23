import { serverGet } from "@/lib/api/server";
import type { HealthDietLog } from "@/lib/api/types";

import { BarChart } from "../charts";
import { Card, clock, Empty, PageHeader, RangeTabs, shortDate, Stat } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Diet: the food log, the most-eaten items, and caffeine against the clock.
 *
 * Ported from the dashboard's `diet.html`. The flags are the part worth
 * keeping - the log itself is a list of strings, and what makes it readable is
 * that "flat white" is visibly caffeine and "porridge" is visibly the good
 * kind of breakfast without anyone having to read every row.
 *
 * The caffeine panel is separate from the log because it answers a question
 * about the clock rather than the food: a coffee is unremarkable at 8am and
 * worth noticing at 4pm, and that only shows up when the times are together.
 */

//: Late-afternoon caffeine is the thing this panel exists to surface - the
//: half-life is around five hours, so a 4pm coffee is still working at bedtime.
const LATE_CAFFEINE_HOUR = 14;

const FLAG_TONE: Record<string, string> = {
  watch: "bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/20",
  good: "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20",
};

export default async function DietPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string; q?: string }>;
}) {
  const { days: rawDays, q } = await searchParams;
  const days = Number(rawDays) || 30;
  const search = (q ?? "").trim();

  const log = await serverGet<HealthDietLog>(
    `/health/diet?days=${days}${search ? `&q=${encodeURIComponent(search)}` : ""}`,
  );

  const flagLabel = new Map(log.flag_catalogue.map((f) => [f.key, f]));

  // The zone is not carried per entry here the way it is on the day view, so
  // times are rendered in the browser's own zone via a fixed AU locale. Every
  // entry in this archive was logged in Melbourne.
  const timeZone = "Australia/Melbourne";

  // Bucketed on the *local* hour, never the server's. This renders in UTC, and
  // reading the hour there files a 7am coffee under 21:00 the previous day -
  // which is the entire point of the panel, inverted.
  const localHour = (at: string) => Number(clock(at, timeZone).slice(0, 2));
  const hours: number[] = new Array(24).fill(0);
  for (const entry of log.caffeine) {
    const hour = localHour(entry.at);
    hours[hour] = (hours[hour] ?? 0) + 1;
  }
  const late = log.caffeine.filter((entry) => localHour(entry.at) >= LATE_CAFFEINE_HOUR);

  return (
    <>
      <PageHeader
        title="Diet"
        subtitle={`${log.entries.length} entries${search ? ` matching “${search}”` : ""} over ${days} days.`}
      >
        <RangeTabs
          basePath="/diet"
          current={days}
          options={[
            { days: 7, label: "7d" },
            { days: 30, label: "30d" },
            { days: 90, label: "90d" },
            { days: 365, label: "1y" },
          ]}
          extra={search ? `&q=${encodeURIComponent(search)}` : ""}
        />
      </PageHeader>

      {/* A plain GET form: no client component, no hydration, and the result is
          a shareable URL. The button is never disabled - an empty search simply
          clears the filter, which is a useful thing to do. */}
      <form method="get" className="mb-4 flex gap-2">
        <input type="hidden" name="days" value={days} />
        <input
          type="search"
          name="q"
          defaultValue={search}
          placeholder="Search foods…"
          aria-label="Search foods"
          className="w-full max-w-xs rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white dark:bg-slate-100 dark:text-slate-900"
        >
          Search
        </button>
      </form>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Entries" value={log.entries.length.toLocaleString()} sub={`over ${days} days`} />
        <Stat
          label="Distinct foods"
          value={new Set(log.entries.map((e) => e.name.toLowerCase())).size.toLocaleString()}
        />
        <Stat label="Caffeine" value={log.caffeine.length.toLocaleString()} sub="logged drinks" />
        <Stat
          label={`After ${LATE_CAFFEINE_HOUR}:00`}
          value={late.length.toLocaleString()}
          sub="caffeine late in the day"
          tone={late.length > 0 ? "text-amber-600 dark:text-amber-400" : ""}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Log" subtitle="Newest first.">
            {log.entries.length === 0 ? (
              <Empty>
                {search ? `Nothing matching “${search}”.` : "Nothing logged in this window."}
              </Empty>
            ) : (
              <ol className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {log.entries.map((entry) => (
                  <li key={entry.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
                    <span className="w-20 shrink-0 text-xs tabular-nums text-slate-400 dark:text-slate-600">
                      {shortDate(entry.local_date)}
                    </span>
                    <span className="w-10 shrink-0 text-xs tabular-nums text-slate-400 dark:text-slate-600">
                      {clock(entry.at, timeZone)}
                    </span>
                    <span className="text-sm">{entry.name}</span>
                    {entry.flags.map((key) => {
                      const flag = flagLabel.get(key);
                      if (!flag) return null;
                      return (
                        <span
                          key={key}
                          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${
                            FLAG_TONE[flag.tone] ?? FLAG_TONE.watch
                          }`}
                        >
                          {flag.label}
                        </span>
                      );
                    })}
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card title="Caffeine by hour" subtitle="When the day's caffeine actually lands.">
            <BarChart
              bars={hours.map((count, hour) => ({
                label: `${String(hour).padStart(2, "0")}`,
                value: count,
                title: `${String(hour).padStart(2, "0")}:00 — ${count} drink${count === 1 ? "" : "s"}`,
              }))}
              height={160}
              unit="drinks"
              colour="var(--viz-4)"
            />
            {late.length > 0 && (
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                {late.length} of {log.caffeine.length} after {LATE_CAFFEINE_HOUR}:00. Caffeine has a
                half-life of about five hours, so these are still working at bedtime.
              </p>
            )}
          </Card>
        </div>

        <Card title="Most eaten" subtitle={`Counted over the full ${days} days, not the search.`}>
          {log.top.length === 0 ? (
            <Empty>Nothing logged in this window.</Empty>
          ) : (
            <ol className="space-y-1.5">
              {log.top.map((food) => (
                <li key={food.name} className="flex items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate" title={food.name}>
                    {food.name}
                  </span>
                  <span
                    aria-hidden
                    className="h-1.5 rounded-full"
                    style={{
                      width: `${(food.count / (log.top[0]?.count ?? 1)) * 60}px`,
                      backgroundColor: "var(--viz-1)",
                    }}
                  />
                  <span className="w-8 text-right text-xs tabular-nums text-slate-500">
                    {food.count}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </>
  );
}
