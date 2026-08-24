"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { HealthBodyProfile } from "@/lib/api/types";

/**
 * The three forms that write to this page: a weight, a tape measure, and the
 * two profile numbers everything else is derived against.
 *
 * The only client components on the page. Everything else is server-rendered,
 * so hydration pays for the four inputs that genuinely need it and nothing
 * more.
 *
 * **Every field is a plain native input.** `type="number"` with `inputMode`
 * decimal gets the numeric keypad on a phone, and `type="date"` gets the
 * platform's own picker - which is the same decision the profile's birthdate
 * made and the reason there is no date-picker dependency in this project.
 *
 * **Backdating is on the weight and the measurement, not the profile.** A
 * weigh-in you forgot to enter on Sunday belongs to Sunday: `local_date` is
 * stored rather than computed, so filing it today would put it on the wrong
 * row of the table permanently. A height has no date - it is the current
 * value every past BMI is recomputed against.
 */

/** Blank means "not entered", which is different from zero. */
function parse(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function Field({
  label,
  value,
  onChange,
  unit,
  step = "0.1",
  type = "number",
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  unit?: string;
  step?: string;
  type?: string;
}) {
  return (
    <label className="text-xs text-ink-dim">
      {label}
      {unit && <span className="ml-1 text-ink-muted">({unit})</span>}
      <input
        type={type}
        inputMode={type === "number" ? "decimal" : undefined}
        step={type === "number" ? step : undefined}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink tabular-nums outline-none focus:border-brand-blue"
      />
    </label>
  );
}

function Submit({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      // Only ever disabled while a request is in flight. A field left blank is
      // explained by the click, not by a button that absorbs it in silence.
      className="rounded-lg bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40"
    >
      {busy ? "Saving…" : children}
    </button>
  );
}

/** Shared submit plumbing: one in-flight flag, one error, one refresh. */
function useRecorder() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function submit(action: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      setNote(await action());
      // The chart, the stat tiles and the table are all server-rendered from
      // the same request, so one refresh moves every one of them. Without it
      // the number you just typed is the only thing on the page that knows.
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not save");
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, note, submit };
}

function Feedback({ error, note }: { error: string | null; note: string | null }) {
  if (error) {
    return (
      <p role="alert" className="mt-3 text-sm text-critical">
        {error}
      </p>
    );
  }
  return note ? <p className="mt-3 text-sm text-ink-dim">{note}</p> : null;
}

export function RecordWeight() {
  const { busy, error, note, submit } = useRecorder();
  const [weight, setWeight] = useState("");
  const [on, setOn] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const value = parse(weight);
        if (value === undefined) {
          return void submit(async () => {
            throw new Error("Enter a weight in kilograms.");
          });
        }
        void submit(async () => {
          await apiSend("/health/body/weight", {
            body: { weight_kg: value, on: on || null },
          });
          setWeight("");
          setOn("");
          return `Recorded ${value} kg.`;
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Weight" unit="kg" value={weight} onChange={setWeight} />
        <Field label="Date" type="date" value={on} onChange={setOn} />
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Leave the date blank for today. Two weigh-ins on one day are two readings of a number that
        moved, not two samples of one — the later one is what the chart plots.
      </p>
      <div className="mt-3">
        <Submit busy={busy}>Record weight</Submit>
      </div>
      <Feedback error={error} note={note} />
    </form>
  );
}

export function RecordMeasurement() {
  const { busy, error, note, submit } = useRecorder();
  const [waist, setWaist] = useState("");
  const [hips, setHips] = useState("");
  const [neck, setNeck] = useState("");
  const [fat, setFat] = useState("");
  const [on, setOn] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void submit(async () => {
          const body = {
            waist_cm: parse(waist),
            hips_cm: parse(hips),
            neck_cm: parse(neck),
            body_fat_pct: parse(fat),
            on: on || null,
          };
          if (
            body.waist_cm === undefined &&
            body.hips_cm === undefined &&
            body.neck_cm === undefined &&
            body.body_fat_pct === undefined
          ) {
            throw new Error("Enter at least one measurement.");
          }
          await apiSend("/health/body/measurement", { body });
          setWaist("");
          setHips("");
          setNeck("");
          setFat("");
          setOn("");
          return "Measurement recorded.";
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Waist" unit="cm" value={waist} onChange={setWaist} />
        <Field label="Hips" unit="cm" value={hips} onChange={setHips} />
        <Field label="Neck" unit="cm" value={neck} onChange={setNeck} />
        <Field label="Body fat" unit="%" value={fat} onChange={setFat} />
        <Field label="Date" type="date" value={on} onChange={setOn} />
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Fill in only what you measured — a blank field is not recorded as zero. Measure the waist at
        the midpoint between the lowest rib and the top of the hip bone, at the end of a normal
        breath out; a tape held somewhere different each time measures the tape, not you.
      </p>
      <div className="mt-3">
        <Submit busy={busy}>Record measurement</Submit>
      </div>
      <Feedback error={error} note={note} />
    </form>
  );
}

export function RecordProfile({ initial }: { initial: HealthBodyProfile }) {
  const { busy, error, note, submit } = useRecorder();
  const [height, setHeight] = useState(initial.height_cm ? String(initial.height_cm) : "");
  const [target, setTarget] = useState(
    initial.target_weight_kg ? String(initial.target_weight_kg) : "",
  );

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void submit(async () => {
          // Both keys are always sent, and a blank field sends an explicit
          // null rather than being omitted: on this form, clearing a box is
          // how you unset the value. The API distinguishes the two, so an
          // omitted key here would make the field impossible to clear.
          await apiSend<HealthBodyProfile>("/health/body/profile", {
            method: "PATCH",
            body: {
              height_cm: parse(height) ?? null,
              target_weight_kg: parse(target) ?? null,
            },
          });
          return "Saved.";
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Height" unit="cm" value={height} onChange={setHeight} />
        <Field label="Target weight" unit="kg" value={target} onChange={setTarget} />
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Height in centimetres, not metres — it is the denominator of every BMI and every
        waist-to-height ratio on this page. The target weight is your own number: setting one is
        what gives the weight column a colour, and clearing it takes the colour away rather than
        substituting a population threshold that does not exist.
      </p>
      <div className="mt-3">
        <Submit busy={busy}>Save</Submit>
      </div>
      <Feedback error={error} note={note} />
    </form>
  );
}
