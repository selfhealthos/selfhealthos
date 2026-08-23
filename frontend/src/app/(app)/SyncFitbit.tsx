"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { HealthConnection, HealthSyncQueued } from "@/lib/api/types";

// The "Sync now" control, and what to show when there is nothing to sync yet.
//
// The pull runs on the worker, so this only ever queues: the browser is not
// going to hold a request open for a Fitbit backfill.
//
// The window is a field rather than a fixed default because the two things
// people press this for want different numbers - "did last night land yet" is
// a day or two, "fill in the fortnight I was away" is fourteen. The sync
// itself is what keeps that affordable: everything with a date-range endpoint
// is fetched once for the whole window, and per-day minute data is fetched
// only for days that have none, so a longer window costs little more than a
// short one unless it is genuinely full of gaps.

//: Fitbit's own ceiling is a rate limit rather than a range, but a window this
//: long is a backfill and belongs in the management command, where it can
//: report progress and be resumed.
const MAX_DAYS = 30;

export function SyncFitbit({ connection }: { connection: HealthConnection | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [days, setDays] = useState(7);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!connection?.connected) {
    return (
      <Link
        href="/settings"
        className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium transition hover:border-slate-500 dark:border-slate-600"
      >
        {connection?.status === "expired" ? "Reconnect Fitbit" : "Connect Fitbit"}
      </Link>
    );
  }

  async function sync() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await apiSend<HealthSyncQueued>(
        `/health/connections/fitbit/sync?days=${days}`,
      );
      setNote(result?.message ?? "Queued.");
      // Picks up last_sync_at; the data itself lands when the worker finishes.
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the sync");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="text-right">
      <div className="flex items-center justify-end gap-1.5">
        <label htmlFor="sync-days" className="text-xs text-slate-500 dark:text-slate-400">
          Last
        </label>
        <input
          id="sync-days"
          type="number"
          min={1}
          max={MAX_DAYS}
          value={days}
          onChange={(event) => {
            // Clamped here rather than only by `min`/`max`, which browsers
            // enforce on the spinner and not on typing.
            const parsed = Number(event.target.value);
            setDays(Number.isFinite(parsed) ? Math.min(MAX_DAYS, Math.max(1, parsed)) : 7);
          }}
          className="w-14 rounded-lg border border-slate-300 bg-transparent px-2 py-1 text-right text-xs tabular-nums dark:border-slate-600"
        />
        <span className="text-xs text-slate-500 dark:text-slate-400">days</span>
        <button
          onClick={sync}
          disabled={busy}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium transition hover:border-slate-500 disabled:opacity-40 dark:border-slate-600"
        >
          {busy ? "Starting…" : "Sync Fitbit"}
        </button>
      </div>
      {note && <p className="mt-1 text-xs text-slate-400">{note}</p>}
      {error && (
        <p role="alert" className="mt-1 text-xs text-rose-600 dark:text-rose-400">
          {error}
        </p>
      )}
      {!note && !error && connection.last_sync_error && (
        <p className="mt-1 max-w-xs text-xs text-amber-600 dark:text-amber-400">
          {connection.last_sync_error}
        </p>
      )}
    </div>
  );
}
