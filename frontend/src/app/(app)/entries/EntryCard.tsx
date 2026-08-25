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
    <div className="w-56 overflow-hidden rounded-xl border border-border bg-surface">
      <div aria-hidden className="h-1" style={{ backgroundColor: colour }} />
      <div className="p-3">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-xs font-semibold tracking-wide text-ink-dim uppercase">
            {entry.label}
          </span>
          <span className="text-xs tabular-nums text-ink-muted">{time}</span>
        </div>
        <p className="text-sm text-ink">{entry.value}</p>

        <div className="mt-2 flex items-center gap-2">
          {confirming ? (
            <>
              <button
                onClick={del}
                disabled={busy}
                className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
              >
                {busy ? "Deleting…" : "Confirm delete"}
              </button>
              <button
                onClick={() => setConfirming(false)}
                disabled={busy}
                className="text-xs text-ink-muted hover:underline"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="text-xs text-ink-muted hover:text-red-600 hover:underline dark:hover:text-red-400"
            >
              Delete
            </button>
          )}
        </div>
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
