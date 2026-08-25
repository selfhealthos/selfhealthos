"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { User } from "@/lib/api/types";

/**
 * The one setting on this page that changes what the data *means*.
 *
 * `local_date` is stored, not computed, so this timezone decides which
 * calendar day every entry is filed under - and every "today" query on every
 * page recomputes its window from the same field. Leave it on the `UTC`
 * column default while living in +10 and a weight saved on Tuesday morning is
 * written under a Tuesday the server still thinks is tomorrow, then filtered
 * back out of the Body page and the entries timeline by their own `<= today`
 * bound. Nothing errors; the page is simply empty.
 *
 * Hence the two affordances beyond the dropdown: the browser's own zone
 * offered as one click (it is right far more often than a list you scroll),
 * and a live clock, because the only check a person can actually perform is
 * whether the time shown matches the clock on their wall.
 */

/** What the browser thinks it is, or null where Intl is unavailable. */
function browserZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

function clockIn(zone: string): string | null {
  try {
    return new Date().toLocaleString(undefined, {
      timeZone: zone,
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return null;
  }
}

/** Group by the part before the first "/" so ~450 options stay scannable. */
function byRegion(zones: string[]): [string, string[]][] {
  const groups = new Map<string, string[]>();
  for (const zone of zones) {
    const region = zone.includes("/") ? zone.slice(0, zone.indexOf("/")) : "Other";
    groups.set(region, [...(groups.get(region) ?? []), zone]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function label(zone: string): string {
  // "Australia/Sydney" -> "Sydney"; "America/Argentina/Salta" -> "Argentina/Salta".
  const rest = zone.slice(zone.indexOf("/") + 1);
  return (zone.includes("/") ? rest : zone).replaceAll("_", " ");
}

export function TimezonePicker({ current, timezones }: { current: string; timezones: string[] }) {
  const router = useRouter();
  const [saved, setSaved] = useState(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Both of these read the *client's* clock and locale, so they must not run
  // during the server render - a mismatch here is a hydration error on a page
  // that is otherwise entirely static.
  const [detected, setDetected] = useState<string | null>(null);
  const [now, setNow] = useState<string | null>(null);

  useEffect(() => setDetected(browserZone()), []);
  useEffect(() => {
    const tick = () => setNow(clockIn(saved));
    tick();
    const id = setInterval(tick, 10_000);
    return () => clearInterval(id);
  }, [saved]);

  // A zone set through the API can be a legacy alias the picker does not
  // offer (`US/Pacific`). Injecting it keeps the select from silently
  // re-selecting its first option and saving a zone nobody chose.
  const options = useMemo(
    () => byRegion(timezones.includes(saved) ? timezones : [...timezones, saved].sort()),
    [timezones, saved],
  );

  async function save(zone: string) {
    const previous = saved;
    setSaved(zone);
    setBusy(true);
    setError(null);
    try {
      await apiSend<User>("/auth/me", { method: "PATCH", body: { timezone: zone } });
      // Every server-rendered page on this layout computed its date window
      // from the old zone, so they are all stale now, not just this one.
      router.refresh();
    } catch (err) {
      setSaved(previous);
      setError(err instanceof Error ? err.message : "Could not save that timezone");
    } finally {
      setBusy(false);
    }
  }

  const mismatched = detected && detected !== saved;

  return (
    <div>
      <label className="block">
        <span className="text-ink-dim text-sm">Timezone</span>
        <select
          value={saved}
          disabled={busy}
          onChange={(event) => save(event.target.value)}
          className="border-border bg-bg text-ink focus:border-brand-blue mt-1 w-full rounded-lg border px-3 py-2 text-sm outline-none disabled:opacity-40"
        >
          {options.map(([region, zones]) => (
            <optgroup key={region} label={region}>
              {zones.map((zone) => (
                <option key={zone} value={zone}>
                  {label(zone)}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      <p className="text-ink-muted mt-2 text-xs" aria-live="polite">
        {busy ? (
          "Saving…"
        ) : now ? (
          <>
            It is <span className="text-ink font-medium">{now}</span> in {label(saved)}. If that is
            not the time where you are, pick the city that matches.
          </>
        ) : (
          <>&nbsp;</>
        )}
      </p>

      {mismatched && (
        <button
          type="button"
          onClick={() => save(detected)}
          disabled={busy}
          className="border-border text-ink hover:border-brand-blue mt-3 rounded-lg border px-3 py-1.5 text-sm transition disabled:opacity-40"
        >
          Use my browser&apos;s timezone ({label(detected)})
        </button>
      )}

      {error && <p className="text-critical mt-2 text-xs">{error}</p>}
    </div>
  );
}
