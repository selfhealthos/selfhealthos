import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthEntriesDay } from "@/lib/api/types";

import { Card, clock, Empty, PageHeader, shortDate } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Entries: everything hand-logged on one day, in the order it happened.
 *
 * One flat timeline across every entry type - diet, exercise, gut, vitals,
 * notes, documents, body measurements, fitness tests - rather than each
 * getting its own page's worth of history. `services.entries_for_day` is
 * what does the flattening; this page is just the calendar day picker and
 * the layout.
 *
 * No "today" special-casing for the pager: paging past today just shows an
 * empty day, the same as paging before any data exists. Both are correct,
 * and it avoids the page needing its own opinion about what day it is versus
 * the one the API already resolved.
 */

const TIME_ZONE = "Australia/Melbourne";

//: Fixed per entry type, from the app's own categorical ramp - a 9th type
//: (fitness_test) falls back to a brand colour rather than reusing a slot,
//: since color here is a secondary accent, not the primary identifier (the
//: label at the top of each card already states the type in words).
const TYPE_COLOURS: Record<string, string> = {
  diet: "var(--viz-1)",
  exercise: "var(--viz-2)",
  gut: "var(--viz-3)",
  vitals_bp: "var(--viz-4)",
  vitals_weight: "var(--viz-5)",
  note: "var(--viz-6)",
  doc: "var(--viz-7)",
  body: "var(--viz-8)",
  fitness_test: "var(--color-brand-teal)",
};

function shiftDate(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const at = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + delta));
  return at.toISOString().slice(0, 10);
}

export default async function EntriesPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date: raw } = await searchParams;
  const requested = raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null;

  const day = await serverGet<HealthEntriesDay>(
    `/health/entries${requested ? `?on=${requested}` : ""}`,
  );

  return (
    <>
      <PageHeader
        title="Entries"
        subtitle={`Everything logged on ${shortDate(day.date)}, earliest first.`}
      >
        <div className="flex items-center gap-1" role="group" aria-label="Other days">
          <Link
            href={`/entries?date=${shiftDate(day.date, -1)}`}
            rel="prev"
            className="rounded-md border border-border px-2.5 py-1 text-xs text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
          >
            ← Previous
          </Link>
          <Link
            href={`/entries?date=${shiftDate(day.date, 1)}`}
            rel="next"
            className="rounded-md border border-border px-2.5 py-1 text-xs text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Next →
          </Link>
        </div>
      </PageHeader>

      {day.entries.length === 0 ? (
        <Card>
          <Empty>Nothing logged on this day.</Empty>
        </Card>
      ) : (
        <div className="flex flex-wrap gap-3">
          {day.entries.map((entry) => (
            <div
              key={entry.id}
              className="w-56 overflow-hidden rounded-xl border border-border bg-surface"
            >
              <div
                aria-hidden
                className="h-1"
                style={{ backgroundColor: TYPE_COLOURS[entry.type] ?? "var(--viz-1)" }}
              />
              <div className="p-3">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold tracking-wide text-ink-dim uppercase">
                    {entry.label}
                  </span>
                  <span className="text-xs tabular-nums text-ink-muted">
                    {clock(entry.at, TIME_ZONE)}
                  </span>
                </div>
                <p className="text-sm text-ink">{entry.value}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
