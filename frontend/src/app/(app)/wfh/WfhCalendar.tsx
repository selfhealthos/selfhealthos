"use client";

import Link from "next/link";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { HealthOfficeDay } from "@/lib/api/types";

/**
 * The clickable grid. A day is either marked or it isn't - clicking calls the
 * PUT/DELETE pair on `/office/days/{date}` and trusts the response's `worked`
 * over the optimistic guess, so a request that actually failed (or a second
 * click landing mid-flight) can't leave the UI showing something the server
 * doesn't have.
 */

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** JS `getUTCDay()` is 0=Sun..6=Sat; the grid's columns are 0=Mon..6=Sun. */
function leadingBlanks(year: number, month: number): number {
  const weekday = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
  return (weekday + 6) % 7;
}

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function WfhCalendar({
  month,
  monthLabel,
  prevHref,
  nextHref,
  initialMarked,
}: {
  /** "YYYY-MM" */
  month: string;
  /** "August 2026" */
  monthLabel: string;
  prevHref: string;
  nextHref: string;
  /** ISO dates within `month` already marked worked-in-office. */
  initialMarked: string[];
}) {
  const [marked, setMarked] = useState(() => new Set(initialMarked));
  const [pending, setPending] = useState<string | null>(null);

  const [yearStr, monthStr] = month.split("-");
  const year = Number(yearStr);
  const monthNum = Number(monthStr);
  const total = daysInMonth(year, monthNum);
  const blanks = leadingBlanks(year, monthNum);
  const today = todayIso();

  async function toggle(date: string) {
    if (pending) return;
    const wasMarked = marked.has(date);
    setPending(date);
    setMarked((prev) => {
      const next = new Set(prev);
      if (wasMarked) next.delete(date);
      else next.add(date);
      return next;
    });
    try {
      const result = await apiSend<HealthOfficeDay>(`/health/office/days/${date}`, {
        method: wasMarked ? "DELETE" : "PUT",
      });
      setMarked((prev) => {
        const next = new Set(prev);
        if (result?.worked) next.add(date);
        else next.delete(date);
        return next;
      });
    } catch {
      // The click didn't take - put it back the way it was.
      setMarked((prev) => {
        const next = new Set(prev);
        if (wasMarked) next.add(date);
        else next.delete(date);
        return next;
      });
    } finally {
      setPending(null);
    }
  }

  const cells: Array<{ day: number; date: string } | null> = [
    ...Array.from({ length: blanks }, () => null),
    ...Array.from({ length: total }, (_, index) => {
      const day = index + 1;
      return { day, date: `${month}-${String(day).padStart(2, "0")}` };
    }),
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Link
            href={prevHref}
            aria-label="Previous month"
            className="flex size-8 items-center justify-center rounded-md text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
          >
            ‹
          </Link>
          <h2 className="w-40 text-center text-base font-bold text-ink">{monthLabel}</h2>
          <Link
            href={nextHref}
            aria-label="Next month"
            className="flex size-8 items-center justify-center rounded-md text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
          >
            ›
          </Link>
        </div>

        <div className="flex items-center gap-2 text-xs text-ink-dim">
          <span aria-hidden className="inline-block size-2.5 rounded-full bg-ink" />
          Office
          <span className="font-medium text-ink">
            {marked.size} day{marked.size === 1 ? "" : "s"} in office
          </span>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-y-2 text-center">
        {WEEKDAYS.map((label) => (
          <p key={label} className="text-xs font-medium text-ink-muted">
            {label}
          </p>
        ))}

        {cells.map((cell, index) => {
          if (!cell) return <div key={`blank-${index}`} />;
          const isMarked = marked.has(cell.date);
          const isToday = cell.date === today;
          return (
            <div key={cell.date} className="flex items-center justify-center py-0.5">
              <button
                type="button"
                onClick={() => toggle(cell.date)}
                disabled={pending === cell.date}
                aria-pressed={isMarked}
                aria-label={`${cell.date}${isMarked ? ", worked in office" : ""}`}
                className={`flex size-10 items-center justify-center rounded-full text-sm transition-colors disabled:opacity-60 ${
                  isMarked
                    ? "bg-ink font-medium text-bg"
                    : isToday
                      ? "text-ink ring-2 ring-inset ring-ink-muted"
                      : "text-ink-dim hover:bg-surface-2"
                }`}
              >
                {cell.day}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
