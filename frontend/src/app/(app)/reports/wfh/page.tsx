import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthOfficeReport } from "@/lib/api/types";

import { Card, Empty, PageHeader, RangeTabs, shortDate, Stat } from "../../ui";
import { BUCKETS, bestBucket, DayTypeLegend, fmtMetricValue, SwingRow } from "./SwingChart";

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

const SWING_HIGHLIGHTS = 6;

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
  const highlights = report.metrics.slice(0, SWING_HIGHLIGHTS);

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
            <>
              <Card
                title="Biggest swings"
                subtitle="The metrics that differ most between day types, ranked by how large the swing is relative to the metric's own scale."
              >
                <DayTypeLegend />
                <div className="divide-y divide-border">
                  {highlights.map((metric) => (
                    <SwingRow key={metric.metric} metric={metric} />
                  ))}
                </div>
              </Card>

              <Card
                title="Every metric"
                subtitle="All tracked metrics with enough data in at least two buckets to compare. Bold is the better bucket, for the handful of metrics with an undisputed direction."
              >
                <div className="overflow-x-auto">
                  <table className="w-full border-separate border-spacing-0 text-sm">
                    <thead>
                      <tr>
                        <th className="border-b border-border px-2 py-2 text-left text-xs font-semibold text-ink-dim">
                          Metric
                        </th>
                        {BUCKETS.map((bucket) => (
                          <th
                            key={bucket.key}
                            className="border-b border-border px-2 py-2 text-right text-xs font-semibold text-ink-dim"
                          >
                            {bucket.label}
                          </th>
                        ))}
                        <th className="border-b border-border px-2 py-2 text-right text-xs font-semibold text-ink-dim">
                          Swing
                        </th>
                      </tr>
                    </thead>
                    <tbody className="text-ink">
                      {report.metrics.map((metric) => {
                        const best = bestBucket(metric);
                        return (
                          <tr key={metric.metric}>
                            <td className="border-b border-border/60 px-2 py-1.5 whitespace-nowrap">
                              {metric.label}
                            </td>
                            {BUCKETS.map((bucket) => {
                              const value = metric[bucket.key];
                              return (
                                <td
                                  key={bucket.key}
                                  className={`border-b border-border/60 px-2 py-1.5 text-right text-xs tabular-nums ${
                                    best === bucket.key ? "font-semibold text-ink" : "text-ink-dim"
                                  }`}
                                >
                                  {value === null || value === undefined
                                    ? "—"
                                    : fmtMetricValue(value, metric.unit)}
                                </td>
                              );
                            })}
                            <td className="border-b border-border/60 px-2 py-1.5 text-right text-xs tabular-nums text-ink-muted">
                              {metric.swing_pct === null || metric.swing_pct === undefined
                                ? "—"
                                : `${Math.round(metric.swing_pct)}%`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
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
