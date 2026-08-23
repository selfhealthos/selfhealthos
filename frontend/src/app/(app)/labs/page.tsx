import { serverGet } from "@/lib/api/server";
import type { HealthLabMarker } from "@/lib/api/types";

import { LineChart } from "../charts";
import { Card, Empty, num, PageHeader, shortDate } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Labs: blood markers grouped by name, each with its own history.
 *
 * No time window. A blood test happens twice a year, so a "last 30 days"
 * control would produce an empty page on almost every day of the year — the
 * whole history is the useful view, and it is small.
 *
 * **No reference ranges.** They vary by laboratory, by assay and by the person,
 * and printing a green/red band from a hard-coded table is how a normal result
 * gets read as alarming. The trend against this person's own history is what
 * this page is for; the pathology report is what carries the range.
 */

export default async function LabsPage() {
  const markers = await serverGet<HealthLabMarker[]>("/health/labs");

  return (
    <>
      <PageHeader
        title="Labs"
        subtitle={
          markers.length > 0
            ? `${markers.length} markers, ${markers.reduce((n, m) => n + m.count, 0)} results.`
            : undefined
        }
      />

      {markers.length === 0 ? (
        <Card>
          <Empty>No blood results recorded. They arrive from the phone app.</Empty>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {markers.map((marker) => {
            const direction =
              marker.results.length >= 2
                ? marker.latest_value - marker.results[marker.results.length - 2]!.value
                : null;
            return (
              <Card
                key={marker.key}
                title={marker.name}
                subtitle={`${marker.count} result${marker.count === 1 ? "" : "s"} · ${num(marker.minimum, 2)}–${num(marker.maximum, 2)}${marker.unit ? ` ${marker.unit}` : ""}`}
              >
                <div className="mb-3 flex items-baseline gap-2">
                  <span className="text-2xl font-bold">{num(marker.latest_value, 2)}</span>
                  {marker.unit && (
                    <span className="text-sm text-slate-500 dark:text-slate-400">{marker.unit}</span>
                  )}
                  <span className="text-xs text-slate-400 dark:text-slate-600">
                    {shortDate(marker.latest_on)}
                  </span>
                  {direction !== null && direction !== 0 && (
                    // Direction only, never a verdict: whether "up" is good
                    // depends entirely on the marker, and this page does not
                    // know which one it is holding.
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {direction > 0 ? "▲" : "▼"} {num(Math.abs(direction), 2)} since the previous
                    </span>
                  )}
                </div>

                {marker.results.length > 1 ? (
                  <LineChart
                    series={[
                      {
                        label: marker.name,
                        points: marker.results.map((r) => ({ date: r.taken_on, value: r.value })),
                      },
                    ]}
                    height={170}
                    unit={marker.unit}
                  />
                ) : (
                  <p className="py-3 text-center text-xs text-slate-400 dark:text-slate-600">
                    One result — nothing to trend against yet.
                  </p>
                )}

                <table className="mt-3 w-full text-sm">
                  <caption className="sr-only">{marker.name} results</caption>
                  <tbody>
                    {marker.results
                      .slice()
                      .reverse()
                      .map((result) => (
                        <tr
                          key={result.id}
                          className="border-b border-slate-100 last:border-0 dark:border-slate-800/60"
                        >
                          <td className="py-1 text-xs text-slate-500">{shortDate(result.taken_on)}</td>
                          <td className="py-1 text-right tabular-nums">
                            {num(result.value, 2)}
                            {result.unit && (
                              <span className="ml-1 text-xs text-slate-400">{result.unit}</span>
                            )}
                          </td>
                          <td className="py-1 pl-3 text-xs text-slate-500">{result.notes}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
