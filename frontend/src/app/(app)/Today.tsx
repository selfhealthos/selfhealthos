import Link from "next/link";

import type { HealthDay } from "@/lib/api/types";

import { StackedBar } from "./charts";
import { band, Card, clock as clockIn, duration, Stat } from "./ui";

/**
 * The day view, ported from the one-data dashboard's `today.html`.
 *
 * The shape that matters is the **merged timeline**: food and exercise
 * interleaved in clock order rather than kept in separate lists. Two lists side
 * by side cannot answer "what did I eat before that workout", which is the
 * whole reason to look at a day at all.
 *
 * Shared by `/` and `/day/[date]` so the two cannot
 * drift. The cards, stats and status bands come from `ui.tsx`, which every
 * other Health view uses too.
 */

const RECOVERY_TONE: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/20",
  red: "bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/20",
  unknown: "bg-slate-100 text-slate-500 ring-slate-400/20 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-600/30",
};

//: The same tokens the Sleep and Trends pages use, so a night reads the same
//: wherever it appears. Defined in `globals.css`.
const SLEEP_STAGES = [
  { key: "minutes_deep", label: "Deep", color: "var(--viz-stage-deep)" },
  { key: "minutes_rem", label: "REM", color: "var(--viz-stage-rem)" },
  { key: "minutes_light", label: "Light", color: "var(--viz-stage-light)" },
  { key: "minutes_awake", label: "Awake", color: "var(--viz-stage-awake)" },
] as const;

function shiftDate(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const at = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
  at.setUTCDate(at.getUTCDate() + days);
  return at.toISOString().slice(0, 10);
}

export function Today({ day, today }: { day: HealthDay; today: string }) {
  const m = day.metrics;
  // The zone travels with the day for a reason: a server component renders in
  // UTC, and formatting there turns a 7:36am coffee into a 9:36pm one.
  const clock = (iso: string) => clockIn(iso, day.timezone);

  // The merged timeline. Sorted on the raw instant, not the formatted clock
  // string, so 09:00 does not sort after 10:00 as text.
  const timeline = [
    ...day.diet.map((e) => ({ kind: "food" as const, at: e.at, id: e.id, name: e.name })),
    ...day.exercise.map((e) => ({
      kind: "exercise" as const,
      at: e.at,
      id: e.id,
      name: e.name,
      duration_s: e.duration_s,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const habitsDone = day.habits.filter((h) => h.completed).length;
  const isToday = day.date === today;
  const sleep = day.sleep;
  const stages = sleep
    ? sleep.minutes_deep + sleep.minutes_rem + sleep.minutes_light + sleep.minutes_awake
    : 0;

  return (
    <>
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link
            href={`/day/${shiftDate(day.date, -1)}`}
            aria-label="Previous day"
            className="px-1 text-lg text-slate-400 hover:text-slate-900 dark:hover:text-white"
          >
            ‹
          </Link>
          <div>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-semibold ring-1 ring-inset ${
                RECOVERY_TONE[day.recovery.level] ?? RECOVERY_TONE.unknown
              }`}
            >
              {day.recovery.label}
            </span>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {day.date}
              {day.recovery.inputs > 0 && day.recovery.inputs < 3 && (
                <span className="text-slate-400 dark:text-slate-600">
                  {" "}
                  · from {day.recovery.inputs} of 3 readings
                </span>
              )}
              {day.office_day && (
                <span className="text-slate-400 dark:text-slate-600"> · in the office</span>
              )}
            </p>
          </div>
          {day.date < today && (
            <Link
              href={`/day/${shiftDate(day.date, 1)}`}
              aria-label="Next day"
              className="px-1 text-lg text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              ›
            </Link>
          )}
        </div>
        {!isToday && (
          <Link
            href="/"
            className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-500 hover:text-slate-900 dark:border-slate-700 dark:hover:text-white"
          >
            ← Today
          </Link>
        )}
      </header>

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Sleep"
          value={sleep ? duration(sleep.duration_minutes) : null}
          tone={band(sleep?.efficiency, 85, 70)}
          sub={
            sleep ? (
              <>
                {sleep.efficiency ?? "—"}% efficiency · {sleep.minutes_deep}m deep ·{" "}
                {sleep.minutes_rem}m REM
              </>
            ) : undefined
          }
        />
        <Stat
          label="HRV (RMSSD)"
          value={m.hrv_rmssd !== undefined ? Math.round(m.hrv_rmssd * 10) / 10 : null}
          tone={band(m.hrv_rmssd, 65, 45)}
          sub="baseline 65–77"
        />
        <Stat
          label="Steps"
          value={m.steps !== undefined ? Math.round(m.steps).toLocaleString() : null}
          tone={band(m.steps, 10000, 4000)}
          sub={
            m.distance_km !== undefined
              ? `${Math.round(m.distance_km * 10) / 10} km${
                  m.very_active_minutes ? ` · ${Math.round(m.very_active_minutes)}m intense` : ""
                }`
              : undefined
          }
        />
        <Stat
          label="Resting HR"
          value={m.resting_hr !== undefined ? `${Math.round(m.resting_hr)} bpm` : null}
          tone={band(m.resting_hr, 62, 72, false)}
          sub="baseline ~62"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Timeline">
            {timeline.length === 0 ? (
              <p className="text-sm text-slate-400 dark:text-slate-600">
                Nothing logged for this day.
              </p>
            ) : (
              <ol>
                {timeline.map((item, index) => (
                  <li
                    key={item.id}
                    className={`flex items-start gap-3 py-2 ${
                      index > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""
                    }`}
                  >
                    <span className="w-12 shrink-0 pt-0.5 text-xs tabular-nums text-slate-400 dark:text-slate-600">
                      {clock(item.at)}
                    </span>
                    {item.kind === "food" ? (
                      <span className="text-sm">{item.name}</span>
                    ) : (
                      <span className="text-sm text-emerald-600 dark:text-emerald-400">
                        {item.name}
                        <span className="ml-2 text-xs text-slate-400 dark:text-slate-600">
                          {duration(item.duration_s / 60)}
                        </span>
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {day.gym_sets.length > 0 && (
            <Card title={`Gym · ${day.gym_sets.length} sets`}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                    <th className="pb-2 text-left font-normal">Exercise</th>
                    <th className="pb-2 text-right font-normal">Weight</th>
                    <th className="pb-2 text-right font-normal">Reps</th>
                    <th className="pb-2 text-right font-normal">Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {day.gym_sets.map((set) => (
                    <tr key={set.id} className="border-b border-slate-100 dark:border-slate-800/60">
                      <td className="py-1.5">{set.exercise}</td>
                      <td className="py-1.5 text-right tabular-nums">{set.weight_kg} kg</td>
                      <td className="py-1.5 text-right tabular-nums">{set.reps}</td>
                      <td className="py-1.5 text-right tabular-nums text-slate-500">
                        {Math.round(set.volume_kg)} kg
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {day.notes.length > 0 && (
            <Card title="Notes">
              <div className="space-y-3">
                {day.notes.map((note) => (
                  <article key={note.id}>
                    <div className="flex items-baseline justify-between gap-3">
                      <h3 className="text-sm font-medium">{note.title || "Untitled"}</h3>
                      <span className="shrink-0 text-xs tabular-nums text-slate-400">
                        {clock(note.at)}
                      </span>
                    </div>
                    {note.content && (
                      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">
                        {note.content}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title={`Habits · ${habitsDone}/${day.habits.length}`}>
            {day.habits.length === 0 ? (
              <p className="text-sm text-slate-400 dark:text-slate-600">No habits defined.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {day.habits.map((habit) => (
                  <li key={habit.id} className="flex items-center gap-2">
                    <span
                      className={
                        habit.completed
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-slate-300 dark:text-slate-700"
                      }
                      aria-hidden
                    >
                      {habit.completed ? "●" : "○"}
                    </span>
                    <span className={habit.completed ? "" : "text-slate-400 dark:text-slate-600"}>
                      {habit.name}
                    </span>
                    <span className="sr-only">{habit.completed ? "done" : "not done"}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {sleep && stages > 0 && (
            <Card title="Sleep breakdown">
              <StackedBar
                className="mb-3"
                segments={SLEEP_STAGES.map((stage) => ({
                  label: stage.label,
                  value: sleep[stage.key],
                  color: stage.color,
                }))}
              />
              <dl className="space-y-1.5 text-sm">
                {(
                  [
                    ["Deep", sleep.minutes_deep],
                    ["REM", sleep.minutes_rem],
                    ["Light", sleep.minutes_light],
                    ["Awake", sleep.minutes_awake],
                    ["Awakenings", sleep.awakenings_count],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="flex justify-between">
                    <dt className="text-slate-500 dark:text-slate-500">{label}</dt>
                    <dd className="tabular-nums">
                      {label === "Awakenings" ? value : `${value}m`}
                    </dd>
                  </div>
                ))}
              </dl>
            </Card>
          )}

          {day.bm.length > 0 && (
            <Card title="Gut">
              <ul className="space-y-1.5 text-sm">
                {day.bm.map((entry) => (
                  <li key={entry.id} className="flex items-center gap-2">
                    <span className="text-xs tabular-nums text-slate-400">{clock(entry.at)}</span>
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-xs ${
                        entry.bristol >= 6
                          ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"
                          : entry.bristol <= 2
                            ? "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300"
                            : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      }`}
                    >
                      Bristol {entry.bristol}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {(day.bp.length > 0 || day.weight.length > 0) && (
            <Card title="Vitals">
              <ul className="space-y-1.5 text-sm">
                {day.bp.map((entry) => (
                  <li key={entry.id} className="flex items-center justify-between gap-2">
                    <span className="text-xs tabular-nums text-slate-400">{clock(entry.at)}</span>
                    <span className="tabular-nums">
                      {entry.systolic}/{entry.diastolic}
                      <span className="ml-1 text-xs text-slate-400">mmHg</span>
                    </span>
                  </li>
                ))}
                {day.weight.map((entry) => (
                  <li key={entry.id} className="flex items-center justify-between gap-2">
                    <span className="text-xs tabular-nums text-slate-400">{clock(entry.at)}</span>
                    <span className="tabular-nums">
                      {entry.weight_kg}
                      <span className="ml-1 text-xs text-slate-400">kg</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
