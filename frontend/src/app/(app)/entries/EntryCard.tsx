"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { HealthEntry } from "@/lib/api/types";

/**
 * One card, plus the delete affordance the timeline is otherwise read-only
 * without - `DELETE /health/entries/{type}/{id}` is the only write this page
 * has ever had (see `services.delete_entry`).
 *
 * Confirmation is a second click inline, not `window.confirm` - a native
 * dialog blocks the render thread and, on this app's own admission (see the
 * browser-automation guidance this repo was built alongside), is exactly the
 * kind of thing that freezes automated interaction with the page. A second
 * button a person can also just not click is enough friction against a
 * mis-tap without that cost.
 */
export function EntryCard({
  entry,
  time,
  colour,
}: {
  entry: HealthEntry;
  time: string;
  colour: string;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function del() {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/health/entries/${entry.type}/${entry.id}`, { method: "DELETE" });
      // The card itself, and anything else the day's data feeds (a chart on
      // another page, say) - one refresh moves all of it, the same reasoning
      // as body/RecordBody.tsx's useRecorder.
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete");
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <div className="relative w-56 overflow-hidden rounded-xl border border-border bg-surface">
      <div aria-hidden className="h-1" style={{ backgroundColor: colour }} />

      {/* Top-right corner, above everything else on the card. Confirming
          widens it into two tiny targets rather than replacing the × in
          place, so a person who moves to tap confirm doesn't have to
          re-aim at a button that swapped out from under their finger. */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
        {confirming ? (
          <>
            <button
              onClick={del}
              disabled={busy}
              aria-label="Confirm delete"
              title="Confirm delete"
              className="rounded-full bg-red-600 px-2 py-0.5 text-xs font-medium text-white disabled:opacity-50"
            >
              {busy ? "…" : "Confirm"}
            </button>
            <button
              onClick={() => setConfirming(false)}
              disabled={busy}
              aria-label="Cancel"
              title="Cancel"
              className="flex size-5 items-center justify-center rounded-full bg-surface-2 text-ink-muted hover:text-ink"
            >
              ×
            </button>
          </>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            aria-label="Delete entry"
            title="Delete entry"
            className="flex size-5 items-center justify-center rounded-full bg-surface-2 text-sm leading-none text-ink-muted hover:bg-red-600 hover:text-white"
          >
            ×
          </button>
        )}
      </div>

      <div className="p-3">
        <div className="mb-1.5 flex items-center justify-between gap-2 pr-6">
          <span className="text-xs font-semibold tracking-wide text-ink-dim uppercase">
            {entry.label}
          </span>
          <span className="text-xs tabular-nums text-ink-muted">{time}</span>
        </div>
        <p className="text-sm text-ink">{entry.value}</p>
        {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
      </div>
      {entry.image_url && (
        <a href={entry.image_url} target="_blank" rel="noreferrer">
          {/* Plain <img>: a same-origin user upload of unknown dimensions, so
              next/image's resizing pipeline and its width/height requirement
              buy nothing here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={entry.image_url} alt={entry.value} className="h-32 w-full object-cover" />
        </a>
      )}
    </div>
  );
}
