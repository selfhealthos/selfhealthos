import Link from "next/link";

import { shortDate } from "../ui";

/**
 * Paging between nights.
 *
 * The dates come from the API rather than being `date ± 1`, because a night
 * the watch was not worn has no session and stepping by the calendar would
 * land on a 404 — on exactly the gaps someone is paging *past*. An arrow that
 * renders here always leads to a night that exists.
 *
 * Older is left and newer is right, matching every time axis on these pages.
 * At the ends the arrow is not a greyed-out button: a disabled control absorbs
 * the click and explains nothing, so it says which end you are at instead.
 */

const BASE = "rounded-md px-2.5 py-1 text-xs whitespace-nowrap transition-colors";
const LINK =
  "border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800";
const END = "border border-dashed border-slate-200 text-slate-400 dark:border-slate-800 dark:text-slate-600";

export function NightPager({
  previous,
  next,
}: {
  previous?: string | null;
  next?: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Other nights">
      {previous ? (
        <Link href={`/sleep/${previous}`} className={`${BASE} ${LINK}`} rel="prev">
          ← {shortDate(previous)}
        </Link>
      ) : (
        <span className={`${BASE} ${END}`}>← no earlier night</span>
      )}
      {next ? (
        <Link href={`/sleep/${next}`} className={`${BASE} ${LINK}`} rel="next">
          {shortDate(next)} →
        </Link>
      ) : (
        <span className={`${BASE} ${END}`}>latest night →</span>
      )}
    </div>
  );
}
