import { serverGet } from "@/lib/api/server";
import type { HealthDay } from "@/lib/api/types";

import { SyncFitbit } from "./SyncFitbit";
import { Today } from "./Today";

import type { HealthConnection } from "@/lib/api/types";

export const dynamic = "force-dynamic";

/**
 * The Health landing page: the most recent day holding data.
 *
 * Not literally today. Opening this at 6am, before the watch has synced and
 * before anything has been logged, would otherwise show an empty page — so
 * `/health/today` resolves to the latest day that actually has something on
 * it. The header still says which day that is.
 */
export default async function HealthPage() {
  const [day, connections] = await Promise.all([
    serverGet<HealthDay>("/health/today"),
    serverGet<HealthConnection[]>("/health/connections").catch(() => []),
  ]);

  const fitbit = connections.find((c) => c.provider === "fitbit") ?? null;
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <div className="mb-4 flex justify-end">
        <SyncFitbit connection={fitbit} />
      </div>
      <Today day={day} today={today} />
    </>
  );
}
