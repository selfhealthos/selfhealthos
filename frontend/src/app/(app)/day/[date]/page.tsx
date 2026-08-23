import { notFound } from "next/navigation";

import { serverGetOrNull } from "@/lib/api/server";
import type { HealthDay } from "@/lib/api/types";

import { Today } from "../../Today";

export const dynamic = "force-dynamic";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * One named day. The arrows on the day view walk through these.
 *
 * A day with nothing on it is a valid answer, not a 404 — the API returns an
 * empty day and the page says so. Only a malformed date is refused, and here
 * rather than at the API, so a typo in the URL cannot reach the backend as a
 * date parse error.
 */
export default async function HealthDayPage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  if (!ISO_DATE.test(date)) notFound();

  const day = await serverGetOrNull<HealthDay>(`/health/days/${date}`);
  if (!day) notFound();

  const today = new Date().toISOString().slice(0, 10);
  return <Today day={day} today={today} />;
}
