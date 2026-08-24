import type { HealthBodyCell, HealthBodyColumn, HealthBodyRow } from "@/lib/api/types";

import { Empty, num, shortDate } from "../ui";

/**
 * The scored table under the chart: readings down, measures across.
 *
 * Same machinery as `/heatmap` and deliberately the same look — the colour
 * comes from `scoring.py` thresholds with their evidence attached, and the
 * page does no judging of its own. What differs is the row: the heatmap has
 * one per calendar day, this has one per day something was actually recorded.
 * A waist is measured every few weeks, so a row per day would be a table that
 * is mostly em-dashes.
 *
 * **Every cell shows its number.** The colour is a second encoding, never the
 * only one: red-green is the ramp a colourblind reader cannot decode, and the
 * relief for using it anyway is that nothing here is communicated by hue
 * alone. The column header carries its evidence as a tooltip, so "says who?"
 * is answerable without leaving the page.
 */

const BAND_LABELS = ["poor", "below par", "fair", "good", "excellent"] as const;

function fillFor(band: number | null | undefined): string | undefined {
  return band ? `var(--viz-score-${band})` : undefined;
}

function bandName(band: number | null | undefined): string {
  return (band && BAND_LABELS[band - 1]) || "not scored";
}

function display(cell: HealthBodyCell, column: HealthBodyColumn): string {
  if (cell.value === null || cell.value === undefined) return "—";
  return num(cell.value, column.places);
}

export function BodyTable({
  columns,
  rows,
}: {
  columns: HealthBodyColumn[];
  rows: HealthBodyRow[];
}) {
  if (rows.length === 0) {
    return <Empty>Nothing recorded in this window. Use the forms above to add a reading.</Empty>;
  }

  return (
    <div className="max-h-[70vh] overflow-auto">
      <table className="w-full border-separate border-spacing-0 text-sm">
        <caption className="sr-only">
          Body composition readings, each scored against its published threshold.
        </caption>
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky top-0 left-0 z-30 border-b border-border bg-surface px-3 py-2 text-left text-xs font-semibold text-ink"
            >
              Date
            </th>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className="sticky top-0 z-20 border-b border-border bg-surface px-2 py-2 text-center text-xs font-semibold whitespace-nowrap text-ink"
                title={column.evidence}
              >
                {column.label}
                {column.unit && (
                  <span className="ml-1 font-normal text-ink-muted">{column.unit}</span>
                )}
                {/* An unscored column says so in its header rather than just
                    arriving colourless: a blank column and a column with no
                    threshold look identical, and only one of them is fixable. */}
                {!column.scored && (
                  <span className="ml-1 font-normal text-ink-muted" title={column.evidence}>
                    ·
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-ink">
          {rows.map((row) => (
            <tr key={row.date}>
              <th
                scope="row"
                className="sticky left-0 z-10 border-b border-border/60 bg-surface px-3 py-1 text-left text-xs font-normal whitespace-nowrap tabular-nums text-ink-dim"
              >
                {shortDate(row.date)}
              </th>
              {row.cells.map((cell, index) => {
                const column = columns[index];
                if (!column) return null;
                return (
                  <td
                    key={cell.key}
                    className="border-b border-l border-border/60 px-2 py-1 text-center text-xs tabular-nums"
                    style={{ backgroundColor: fillFor(cell.band) }}
                    title={`${column.label} — ${shortDate(row.date)}: ${display(cell, column)}${
                      column.unit ? ` ${column.unit}` : ""
                    } (${bandName(cell.band)})`}
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
  );
}

export function BandLegend() {
  return (
    <ol className="flex flex-wrap gap-2">
      {BAND_LABELS.map((label, index) => (
        <li key={label} className="flex items-center gap-1.5 text-xs text-ink-dim">
          <span
            aria-hidden
            className="inline-block size-4 rounded-sm"
            style={{ backgroundColor: fillFor(index + 1) }}
          />
          {label}
        </li>
      ))}
      <li className="flex items-center gap-1.5 text-xs text-ink-dim">
        <span aria-hidden className="inline-block size-4 rounded-sm border border-border" />
        no reading, or no threshold worth applying
      </li>
    </ol>
  );
}
