import Link from "next/link";

/**
 * The activity page's window control.
 *
 * Same shape as the heart page's, and the same split: one day is the minute
 * climb, a week or more is the trend. They live on one route because they
 * answer the same question at different zoom levels - "did I move enough" -
 * and because "today" is where you land and "the month" is where you go next.
 */

export const WINDOWS = [
  { days: 1, label: "1 day" },
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
] as const;

const BASE = "rounded-md px-2.5 py-1 text-xs transition-colors whitespace-nowrap";
const ACTIVE = "bg-slate-900 font-medium text-white dark:bg-slate-100 dark:text-slate-900";
const IDLE =
  "border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800";

export function ActivityTabs({ current }: { current: number }) {
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Activity view">
      {WINDOWS.map((window) => (
        <Link
          key={window.days}
          href={`/activity?days=${window.days}`}
          aria-current={current === window.days ? "true" : undefined}
          className={`${BASE} ${current === window.days ? ACTIVE : IDLE}`}
        >
          {window.label}
        </Link>
      ))}
    </div>
  );
}
