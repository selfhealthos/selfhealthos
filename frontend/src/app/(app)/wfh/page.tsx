import { serverGet } from "@/lib/api/server";
import type { HealthOffice } from "@/lib/api/types";

import { Card, PageHeader } from "../ui";
import { WfhCalendar } from "./WfhCalendar";

export const dynamic = "force-dynamic";

/**
 * WFH: the write side of the office-day record.
 *
 * `OfficeDay` has always been readable on the Report page (`/office`) - the
 * data just had no way in except a phone sync. `DeviceEntry` was built to
 * allow portal-created rows from the start (no `client_id`, since there is no
 * phone-side row to reconcile against), so this page is that path finally
 * getting a UI: tap a day, `PUT`/`DELETE` `/health/office/days/{date}`, done.
 */

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Decorative default only - "this month" doesn't need to be exact to the
 * minute, so the server's own clock is fine here. */
function currentMonth(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
}

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const at = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1 + delta, 1));
  return `${at.getUTCFullYear()}-${String(at.getUTCMonth() + 1).padStart(2, "0")}`;
}

export default async function WfhPage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const { month: raw } = await searchParams;
  const month = raw && /^\d{4}-\d{2}$/.test(raw) ? raw : currentMonth();
  const [yearStr, monthStr] = month.split("-");
  const year = Number(yearStr);
  const monthNum = Number(monthStr);

  const office = await serverGet<HealthOffice>(`/health/office?year=${year}`);
  const marked = office.days.filter((day) => day.startsWith(month));

  return (
    <>
      <PageHeader title="WFH" subtitle="Tap a day to record it as a day worked in the office." />

      <Card>
        <WfhCalendar
          month={month}
          monthLabel={`${MONTH_NAMES[monthNum - 1]} ${year}`}
          prevHref={`/wfh?month=${shiftMonth(month, -1)}`}
          nextHref={`/wfh?month=${shiftMonth(month, 1)}`}
          initialMarked={marked}
        />
      </Card>
    </>
  );
}
