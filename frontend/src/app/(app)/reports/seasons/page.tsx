import { serverGet } from "@/lib/api/server";
import type { HealthSeasonReport } from "@/lib/api/types";

import { Card, Empty, PageHeader, RangeTabs, shortDate, Stat } from "../../ui";
import { MetricCard } from "./SeasonChart";

export const dynamic = "force-dynamic";

/**
 * Seasons: every metric, averaged by the season its day fell in.
 *
 * Four buckets, and unlike Work From Home's, every day classifies into one -
 * a season is a fact about the calendar, not something that has to be marked
 * first - so there's no "not enough data yet" gate before the grid, only the
 * per-metric one every card in this family already has.
 */

//: "All time" is `days=0` in the URL - a sentinel this page strips before
//: calling the API, where it means "no `days` param", not a real window.
//: Shorter windows than a year are deliberately absent: comparing seasons
//: needs at least one of each to have happened, and a 90-day window almost
//: never spans more than two.
const RANGES = [
  { days: 365, label: "1 year" },
  { days: 1095, label: "3 years" },
  { days: 0, label: "All time" },
] as const;

export default async function SeasonsReportPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const requested = Number(raw);
  const current = RANGES.some((r) => r.days === requested) ? requested : 365;

  const report = await serverGet<HealthSeasonReport>(
    `/health/seasons/report${current ? `?days=${current}` : ""}`,
  );

  return (
    <>
      <PageHeader
        title="Seasons"
        subtitle={`${shortDate(report.start)} – ${shortDate(report.end)}. Every metric averaged by season.`}
      >
        <RangeTabs basePath="/reports/seasons" current={current} options={RANGES} />
      </PageHeader>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Summer days" value={report.days.summer.toLocaleString()} sub="Dec – Feb, in this window" />
          <Stat label="Autumn days" value={report.days.autumn.toLocaleString()} sub="Mar – May, in this window" />
          <Stat label="Winter days" value={report.days.winter.toLocaleString()} sub="Jun – Aug, in this window" />
          <Stat label="Spring days" value={report.days.spring.toLocaleString()} sub="Sep – Nov, in this window" />
        </div>

        {report.metrics.length === 0 ? (
          <Card>
            <Empty>
              Not enough overlapping data yet. Every metric needs enough days in two different
              seasons before an average is worth drawing.
            </Empty>
          </Card>
        ) : (
          // Sorted by `swing_pct` already (see `season_report`), so the
          // metrics that differ most between seasons lead the grid without
          // this page needing its own opinion about ranking.
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {report.metrics.map((metric) => (
              <MetricCard key={metric.metric} metric={metric} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
