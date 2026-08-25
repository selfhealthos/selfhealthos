import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthOfficeReport } from "@/lib/api/types";

import { Card, Empty, PageHeader, RangeTabs, shortDate, Stat } from "../../ui";
import { MetricCard } from "./SwingChart";

export const dynamic = "force-dynamic";

/**
 * Work From Home: every metric, averaged by day type.
 *
 * Three buckets, mutually exclusive - see `office_report` on the backend:
 * weekend days are their own bucket regardless of any office marking, and a
 * weekday only counts as "office" or "wfh" inside the office-day record's
 * covered range. A weekday before that range even started is excluded, not
 * folded into "wfh" - the same "absence means unknown" rule the calendar page
 * states.
 */

//: "All time" is `days=0` in the URL - a sentinel this page strips before
//: calling the API, where it means "no `days` param", not a real window.
const RANGES = [
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
  { days: 0, label: "All time" },
] as const;

export default async function WfhReportPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const requested = Number(raw);
  const current = RANGES.some((r) => r.days === requested) ? requested : 90;

  const report = await serverGet<HealthOfficeReport>(
    `/health/office/report${current ? `?days=${current}` : ""}`,
  );

  const noOfficeDaysYet = report.covers_from === null;

  return (
    <>
      <PageHeader
        title="Work From Home"
        subtitle={`${shortDate(report.start)} – ${shortDate(report.end)}. Every metric averaged by day type.`}
      >
        <RangeTabs basePath="/reports/wfh" current={current} options={RANGES} />
      </PageHeader>

      {noOfficeDaysYet ? (
        <Card>
          <Empty>
            No office days recorded yet. Mark the days you were in the office on the{" "}
            <Link href="/wfh" className="underline hover:no-underline">
              WFH
            </Link>{" "}
            page, and this report will compare them against your days at home.
          </Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Stat
              label="WFH days"
              value={report.days.wfh.toLocaleString()}
              sub="weekdays at home, in this window"
            />
            <Stat
              label="Office days"
              value={report.days.office.toLocaleString()}
              sub="weekdays in the office, in this window"
            />
            <Stat
              label="Weekend days"
              value={report.days.weekend.toLocaleString()}
              sub="Saturdays and Sundays, in this window"
            />
          </div>

          {report.metrics.length === 0 ? (
            <Card>
              <Empty>
                Not enough overlapping data yet. Every metric needs enough days in two different
                buckets before an average is worth drawing.
              </Empty>
            </Card>
          ) : (
            // Sorted by `swing_pct` already (see `office_report`), so the
            // metrics that differ most between day types lead the grid
            // without this page needing its own opinion about ranking.
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {report.metrics.map((metric) => (
                <MetricCard key={metric.metric} metric={metric} />
              ))}
            </div>
          )}

          <p className="text-xs text-ink-muted">
            See the{" "}
            <Link href="/office" className="underline hover:no-underline">
              office-day calendar
            </Link>{" "}
            for the yearly view this report's buckets are built from.
          </p>
        </div>
      )}
    </>
  );
}
