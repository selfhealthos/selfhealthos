import Link from "next/link";

/**
 * The one control the sleep pages share.
 *
 * Two questions get asked of sleep data and they want opposite layouts: "how
 * did I sleep last night" wants one night's chronology at full width, and "how
 * is my sleep this month" wants thirty nights compared. The old page tried to
 * answer both at once, which is why every chart on it was too small to read
 * and nothing on it looked more important than anything else.
 *
 * So the split is a navigation, not a tab component: "Last night" is a
 * different URL with a different page behind it, and the windows are `?days=`
 * on the index. No client state, both halves shareable and bookmarkable, and
 * the back button does what it should.
 */

export const WINDOWS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
] as const;

const BASE =
  "rounded-md px-2.5 py-1 text-xs transition-colors whitespace-nowrap";
const ACTIVE = "bg-slate-900 font-medium text-white dark:bg-slate-100 dark:text-slate-900";
const IDLE =
  "border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800";

export function SleepTabs({
  current,
  latestNight,
}: {
  /** The window in days, or "night" on a single night's page. */
  current: number | "night";
  /** Date of the newest recorded night, if there is one to link to. */
  latestNight?: string | null;
}) {
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Sleep view">
      {/* Disabled controls absorb the click and explain nothing, so with no
          nights recorded this says why instead of going grey. */}
      {latestNight ? (
        <Link
          href={`/sleep/${latestNight}`}
          aria-current={current === "night" ? "true" : undefined}
          className={`${BASE} ${current === "night" ? ACTIVE : IDLE}`}
        >
          Last night
        </Link>
      ) : (
        <span className={`${BASE} border border-dashed border-slate-200 text-slate-400 dark:border-slate-800 dark:text-slate-600`}>
          No nights recorded
        </span>
      )}

      {WINDOWS.map((window) => (
        <Link
          key={window.days}
          href={`/sleep?days=${window.days}`}
          aria-current={current === window.days ? "true" : undefined}
          className={`${BASE} ${current === window.days ? ACTIVE : IDLE}`}
        >
          {window.label}
        </Link>
      ))}
    </div>
  );
}
