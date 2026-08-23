import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthHeatmap, HealthHeatmapCell, HealthHeatmapColumn } from "@/lib/api/types";

import { Card, Empty, num, PageHeader, RangeTabs, shortDate } from "../ui";

export const dynamic = "force-dynamic";

/**
 * The heatmap: days down, metrics across, every cell coloured by how good it is.
 *
 * Ported from the fitcypher dashboard's `heatmap.html`, which is where the
 * layout comes from. What changed is underneath: that page interpolated red to
 * green between a hand-picked min and max per metric, which cannot express a
 * two-sided optimum (it coloured 80 kg green and 60 kg red for everyone) or a
 * plateau (the 9,000th step scored like the 3,000th). The thresholds now live
 * in `backend/apps/health/scoring.py` with their evidence attached, and the
 * cell arrives already scored - the page does no judging of its own, so the
 * same numbers back the API and any future MCP answer.
 *
 * **Every cell shows its number.** The colour is a second encoding, never the
 * only one: red-green is the ramp a colourblind reader cannot decode, and the
 * relief for using it anyway is that nothing here is communicated by hue alone.
 *
 * Rows are days rather than the habit page's transposed grid because a metric
 * is a column you scan down for a run of red, and a day is a row you read
 * across to see what a bad night did to everything else.
 */

const RANGES = [
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
  { days: 180, label: "6mo" },
  { days: 365, label: "1y" },
] as const;

const BAND_LABELS = ["poor", "below par", "fair", "good", "excellent"] as const;

/** The cell's fill. Bandless cells stay on the page background. */
function fillFor(band: number | null | undefined): string | undefined {
  return band ? `var(--viz-score-${band})` : undefined;
}

function bandName(band: number | null | undefined): string {
  return (band && BAND_LABELS[band - 1]) || "not scored";
}

/** The value as it is written in the cell, in the column's own unit. */
function display(cell: HealthHeatmapCell, column: HealthHeatmapColumn): string {
  if (cell.value === null || cell.value === undefined) return "—";
  return num(cell.value, column.places);
}

export default async function HeatmapPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 30;

  const grid = await serverGet<HealthHeatmap>(`/health/heatmap?days=${days}`);
  const { columns, rows } = grid;

  return (
    <>
      <PageHeader
        title="Heatmap"
        subtitle={`${columns.length} metrics over ${rows.length} days with data, to ${grid.end}. Greener is better, against published thresholds.`}
      >
        <RangeTabs basePath="/heatmap" current={days} options={RANGES} />
      </PageHeader>

      {rows.length === 0 ? (
        <Card>
          <Empty>No daily metrics in this window. Sync a wearable or log an entry.</Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card className="p-0">
            {/* The table scrolls inside the card rather than the page: the row
                labels are dates, and a date that scrolls off the left edge
                makes every cell beside it meaningless. */}
            <div className="max-h-[75vh] overflow-auto">
              <table className="w-full border-separate border-spacing-0 text-sm">
                <caption className="sr-only">
                  Daily health metrics from {grid.start} to {grid.end}, each scored against its
                  threshold.
                </caption>
                <thead>
                  <tr>
                    <th
                      scope="col"
                      className="sticky left-0 top-0 z-30 border-b border-slate-200 bg-white px-3 py-2 text-left text-xs font-semibold dark:border-slate-800 dark:bg-slate-900"
                    >
                      Date
                    </th>
                    <th
                      scope="col"
                      className="sticky top-0 z-20 border-b border-slate-200 bg-white px-2 py-2 text-center text-xs font-semibold dark:border-slate-800 dark:bg-slate-900"
                      title="Unweighted mean of the day's scored metrics, as a percentage."
                    >
                      Day
                      <span className="ml-1 font-normal text-slate-400 dark:text-slate-600">%</span>
                    </th>
                    {columns.map((column) => (
                      <th
                        key={column.key}
                        scope="col"
                        className="sticky top-0 z-20 whitespace-nowrap border-b border-slate-200 bg-white px-2 py-2 text-center text-xs font-semibold dark:border-slate-800 dark:bg-slate-900"
                        title={column.evidence}
                      >
                        {column.label}
                        {column.unit && (
                          <span className="ml-1 font-normal text-slate-400 dark:text-slate-600">
                            {column.unit}
                          </span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-slate-900 dark:text-slate-100">
                  {rows.map((row) => (
                    <tr key={row.date}>
                      <th
                        scope="row"
                        className="sticky left-0 z-10 whitespace-nowrap border-b border-slate-100 bg-white px-3 py-1 text-left text-xs font-normal tabular-nums dark:border-slate-800/60 dark:bg-slate-900"
                      >
                        {/* Every row is a link out to the day view: the grid
                            says which day went wrong, and the next question is
                            always what happened on it. */}
                        <Link
                          href={`/day/${row.date}`}
                          className="text-slate-600 hover:underline dark:text-slate-400"
                        >
                          {shortDate(row.date)}
                        </Link>
                      </th>
                      <td
                        className="border-b border-l border-slate-100 px-2 py-1 text-center text-xs font-medium tabular-nums dark:border-slate-800/60"
                        style={{ backgroundColor: fillFor(row.band) }}
                        title={`Day score ${num((row.score ?? 0) * 100, 0)}% — ${bandName(
                          row.band,
                        )}, unweighted mean of ${row.scored_count} metric${
                          row.scored_count === 1 ? "" : "s"
                        }`}
                      >
                        {row.score === null || row.score === undefined
                          ? "—"
                          : num(row.score * 100, 0)}
                      </td>
                      {row.cells.map((cell, index) => {
                        const column = columns[index];
                        if (!column) return null;
                        return (
                          <td
                            key={cell.key}
                            className="border-b border-l border-slate-100 px-2 py-1 text-center text-xs tabular-nums dark:border-slate-800/60"
                            style={{ backgroundColor: fillFor(cell.band) }}
                            title={`${column.label} — ${shortDate(row.date)}: ${display(
                              cell,
                              column,
                            )}${column.unit ? ` ${column.unit}` : ""} (${bandName(cell.band)})`}
                          >
                            {display(cell, column)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card title="Scale" subtitle="Five steps, worst to best. The number in each cell is the measurement itself, never the score.">
              <ol className="flex flex-wrap gap-2">
                {BAND_LABELS.map((label, index) => (
                  <li key={label} className="flex items-center gap-1.5 text-xs">
                    <span
                      aria-hidden
                      className="inline-block size-4 rounded-sm"
                      style={{ backgroundColor: fillFor(index + 1) }}
                    />
                    {label}
                  </li>
                ))}
                <li className="flex items-center gap-1.5 text-xs">
                  <span
                    aria-hidden
                    className="inline-block size-4 rounded-sm border border-slate-200 dark:border-slate-700"
                  />
                  no data, or no threshold worth applying
                </li>
              </ol>
            </Card>

            <Card title="Coverage" subtitle="Days with a value, and the window's average score.">
              <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                {columns.map((column) => (
                  <li key={column.key} className="flex justify-between gap-2">
                    <span className="text-slate-500 dark:text-slate-400">{column.label}</span>
                    <span className="tabular-nums">
                      {column.days}d
                      {column.mean_score !== null && column.mean_score !== undefined && (
                        <span className="ml-1.5 text-slate-400 dark:text-slate-600">
                          {num(column.mean_score * 100, 0)}%
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card
            title="Where the thresholds come from"
            subtitle="Population thresholds, not diagnoses. A red cell is a reason to look, not a finding."
          >
            <dl className="space-y-2 text-xs">
              {columns.map((column) => (
                <div key={column.key} className="sm:flex sm:gap-3">
                  <dt className="shrink-0 font-medium sm:w-32">{column.label}</dt>
                  <dd className="text-slate-500 dark:text-slate-400">{column.evidence}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
      )}
    </>
  );
}
