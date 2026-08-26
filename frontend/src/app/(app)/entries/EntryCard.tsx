"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { HealthEntry } from "@/lib/api/types";

/**
 * One card, plus the two writes this otherwise read-only timeline has:
 * `DELETE` and `PATCH /health/entries/{type}/{id}` (see `services.delete_entry`
 * and `services.update_entry`).
 *
 * Confirmation on delete is a second click inline, not `window.confirm` - a
 * native dialog blocks the render thread and, on this app's own admission (see
 * the browser-automation guidance this repo was built alongside), is exactly
 * the kind of thing that freezes automated interaction with the page. A second
 * button a person can also just not click is enough friction against a
 * mis-tap without that cost.
 *
 * Editing expands the card in place rather than opening a modal: the thing
 * being corrected stays on screen beside the form, and a timeline of small
 * cards has nowhere a modal would sit without covering the neighbours you are
 * comparing against.
 */

//: Which inputs each type shows, mirroring `services._ENTRY_EDITABLE`. The
//: server is still the authority - it rejects a field a type does not own -
//: this only decides what to render. Types with an empty list take a new time
//: and nothing else.
const FIELDS: Record<string, ReadonlyArray<{ key: string; label: string; kind: string }>> = {
  diet: [{ key: "name", label: "Food", kind: "text" }],
  note: [
    { key: "title", label: "Title", kind: "text" },
    { key: "content", label: "Note", kind: "textarea" },
  ],
  gut: [
    { key: "bristol", label: "Bristol (1-7)", kind: "number" },
    { key: "notes", label: "Notes", kind: "text" },
  ],
  vitals_bp: [
    { key: "systolic", label: "Systolic", kind: "number" },
    { key: "diastolic", label: "Diastolic", kind: "number" },
    { key: "notes", label: "Notes", kind: "text" },
  ],
  vitals_weight: [
    { key: "weight_kg", label: "Weight (kg)", kind: "number" },
    { key: "notes", label: "Notes", kind: "text" },
  ],
  exercise: [],
  body: [],
};

/**
 * An instant, as the `datetime-local` input wants it.
 *
 * Deliberately the *browser's* timezone, which is what the native widget
 * means by the numbers it shows. A person editing their own record is
 * normally in the zone that record is kept in; if they are not, the card
 * above still reads in the display zone and the two will disagree.
 */
function toInputValue(iso: string): string {
  const at = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}` +
    `T${pad(at.getHours())}:${pad(at.getMinutes())}`
  );
}

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
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fields = FIELDS[entry.type] ?? [];
  const [at, setAt] = useState(() => toInputValue(entry.at));
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      fields.map((f) => {
        const raw = entry.edit?.[f.key as keyof typeof entry.edit];
        return [f.key, raw === null || raw === undefined ? "" : String(raw)];
      }),
    ),
  );

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

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { at: new Date(at).toISOString() };
      for (const field of fields) {
        const raw = values[field.key] ?? "";
        // Only send what was filled in: the API treats an omitted field as
        // "leave it alone", so a blank optional note must not be sent as an
        // instruction to blank the stored one.
        if (raw === "") continue;
        body[field.key] = field.kind === "number" ? Number(raw) : raw;
      }
      await apiSend(`/health/entries/${entry.type}/${entry.id}`, { method: "PATCH", body });
      setEditing(false);
      // An edited time can move the entry to another day entirely, off this
      // page - refreshing is what makes that visible rather than leaving a
      // card sitting on a day it no longer belongs to.
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-border bg-surface-2 px-2 py-1 text-sm text-ink " +
    "focus:border-ink-muted focus:outline-none";

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
          !editing && (
            <>
              {entry.editable && (
                <button
                  onClick={() => setEditing(true)}
                  aria-label="Edit entry"
                  title="Edit entry"
                  className="flex size-5 items-center justify-center rounded-full bg-surface-2 text-[10px] leading-none text-ink-muted hover:bg-surface hover:text-ink"
                >
                  ✎
                </button>
              )}
              <button
                onClick={() => setConfirming(true)}
                aria-label="Delete entry"
                title="Delete entry"
                className="flex size-5 items-center justify-center rounded-full bg-surface-2 text-sm leading-none text-ink-muted hover:bg-red-600 hover:text-white"
              >
                ×
              </button>
            </>
          )
        )}
      </div>

      <div className="p-3">
        {/* Right padding clears the corner controls, which are one button
            wide on a fixed row and two on an editable one - sized for one,
            the pencil lands on top of the time. */}
        <div
          className={`mb-1.5 flex items-center justify-between gap-2 ${
            entry.editable ? "pr-12" : "pr-6"
          }`}
        >
          <span className="text-xs font-semibold tracking-wide text-ink-dim uppercase">
            {entry.label}
          </span>
          {!editing && <span className="text-xs tabular-nums text-ink-muted">{time}</span>}
        </div>

        {editing ? (
          <div className="flex flex-col gap-2">
            {fields.map((field) => (
              <label key={field.key} className="block">
                <span className="mb-0.5 block text-[10px] tracking-wide text-ink-dim uppercase">
                  {field.label}
                </span>
                {field.kind === "textarea" ? (
                  <textarea
                    rows={3}
                    value={values[field.key] ?? ""}
                    onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                    className={inputClass}
                  />
                ) : (
                  <input
                    type={field.kind === "number" ? "number" : "text"}
                    step="any"
                    value={values[field.key] ?? ""}
                    onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                    className={inputClass}
                  />
                )}
              </label>
            ))}

            <label className="block">
              <span className="mb-0.5 block text-[10px] tracking-wide text-ink-dim uppercase">
                When
              </span>
              {/* Native input, no date-picker dependency - the same call
                  the profile page's birthdate makes. */}
              <input
                type="datetime-local"
                value={at}
                onChange={(e) => setAt(e.target.value)}
                className={inputClass}
              />
            </label>

            <div className="mt-0.5 flex items-center gap-2">
              <button
                onClick={save}
                disabled={busy}
                className="rounded-md bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                {busy ? "Saving…" : "Save"}
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setError(null);
                }}
                disabled={busy}
                className="rounded-md border border-border px-3 py-1 text-xs text-ink-dim hover:bg-surface-2"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink">{entry.value}</p>
        )}

        {/* Only `gym` sends these - one line per set under the exercise name.
            Tabular figures so the weights line up column-wise down the card,
            which is what makes a warm-up ramp readable at a glance. */}
        {!editing && entry.lines.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {entry.lines.map((line, i) => (
              <li key={i} className="text-xs tabular-nums text-ink-dim">
                {line}
              </li>
            ))}
          </ul>
        )}
        {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
      </div>
      {!editing && entry.image_url && (
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
