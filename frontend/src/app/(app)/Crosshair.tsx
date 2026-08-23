"use client";

import { useRef, useState } from "react";

/**
 * A vertical readout line over a chart, and the only client component in the
 * Health app.
 *
 * The charts here are server-rendered SVG with `<title>` tooltips, which is
 * enough for "what is this mark" and useless for the question these stacked
 * charts exist to answer: what were *all* the series doing on the same day.
 * Hovering four panels one at a time and remembering the numbers is not
 * reading a chart. So this draws one line through every panel and puts the
 * whole column's values in one box.
 *
 * **It owns no data.** The columns are computed on the server and passed in
 * already positioned as fractions of the chart's width; this component maps a
 * pointer position onto the nearest one and renders. That keeps the scales in
 * one place - a client-side copy of the x scale would be a second source of
 * truth for where a date sits, and the two would drift.
 *
 * Fractions rather than pixels because the SVG scales with its container: a
 * fraction stays correct at every width, which a pixel offset computed at
 * render time would not.
 */

export type CrosshairRow = { label: string; value: string; colour?: string };

export type CrosshairColumn = {
  /** Position across the chart, 0-1, matching the SVG's own x scale. */
  at: number;
  title: string;
  rows: CrosshairRow[];
};

export function Crosshair({
  columns,
  children,
}: {
  columns: CrosshairColumn[];
  children: React.ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<number | null>(null);

  if (columns.length === 0) return <>{children}</>;

  function locate(clientX: number) {
    const rect = box.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const fraction = (clientX - rect.left) / rect.width;
    // Nearest column rather than a bucket: with gaps in the data - the nights
    // nobody recorded - bucketing lands the reader on an empty slot and shows
    // nothing, when what they meant was "the night nearest here".
    let best = 0;
    let bestGap = Infinity;
    columns.forEach((column, index) => {
      const gap = Math.abs(column.at - fraction);
      if (gap < bestGap) {
        bestGap = gap;
        best = index;
      }
    });
    setActive(best);
  }

  const column = active === null ? null : (columns[active] ?? null);
  // Flip the box to the left of the line once past the middle, so it never
  // hangs off the right edge of the card.
  const flip = column !== null && column.at > 0.6;

  return (
    <div
      ref={box}
      className="relative"
      onPointerMove={(event) => locate(event.clientX)}
      onPointerLeave={() => setActive(null)}
    >
      {children}

      {column && (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 w-px bg-slate-400/70 dark:bg-slate-500/70"
            style={{ left: `${column.at * 100}%` }}
          />
          <div
            className="pointer-events-none absolute top-2 z-10 min-w-36 rounded-lg border border-slate-200 bg-white/95 p-2 text-xs shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
            style={
              flip
                ? { right: `${(1 - column.at) * 100}%`, marginRight: "8px" }
                : { left: `${column.at * 100}%`, marginLeft: "8px" }
            }
          >
            <p className="mb-1 font-medium">{column.title}</p>
            <ul className="space-y-0.5">
              {column.rows.map((row) => (
                <li key={row.label} className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                    {row.colour && (
                      <span
                        aria-hidden
                        className="size-2 rounded-full"
                        style={{ backgroundColor: row.colour }}
                      />
                    )}
                    {row.label}
                  </span>
                  <span className="tabular-nums">{row.value}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
