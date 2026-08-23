import Link from "next/link";

/**
 * The pieces every Health view is built from.
 *
 * Extracted because thirteen pages otherwise carry thirteen slightly different
 * cards, and the drift is invisible until two of them sit side by side. The
 * day view (`Today.tsx`) imports the same `Card` and `Stat` it used to define
 * locally.
 */

export function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-dim">{subtitle}</p>}
      </div>
      {children}
    </header>
  );
}

export function Card({
  title,
  subtitle,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-border bg-surface p-4 ${className}`}>
      {title && (
        <div className="mb-3">
          <h2 className="text-xs font-semibold tracking-wide text-ink-dim uppercase">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "",
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="mb-2 text-xs tracking-wide text-ink-dim uppercase">{label}</p>
      {value === null || value === undefined ? (
        <p className="text-sm text-ink-muted">No data</p>
      ) : (
        <>
          {/* Proportional figures, not tabular: at this size `tabular-nums`
              gives every digit the width of a zero and a number like 121 reads
              loose. Tabular is for columns that have to line up. */}
          <p className={`text-2xl font-bold ${tone || "text-ink"}`}>{value}</p>
          {sub && <p className="mt-1 text-xs text-ink-dim">{sub}</p>}
        </>
      )}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-center text-sm text-ink-muted">{children}</p>;
}

/**
 * The window control every deep-dive page carries.
 *
 * Plain links rather than a client component with state: the data is fetched
 * on the server anyway, so a `?days=` in the URL is both the control and the
 * shareable address of what you are looking at. No hydration, and the back
 * button works.
 */
export function RangeTabs({
  basePath,
  current,
  options,
  param = "days",
  extra = "",
}: {
  basePath: string;
  current: number;
  options: ReadonlyArray<{ days: number; label: string }>;
  param?: string;
  extra?: string;
}) {
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Time range">
      {options.map((option) => {
        const active = option.days === current;
        return (
          <Link
            key={option.days}
            href={`${basePath}?${param}=${option.days}${extra}`}
            aria-current={active ? "true" : undefined}
            className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
              active
                ? "bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple font-medium text-white"
                : "border border-border text-ink-dim hover:bg-surface-2"
            }`}
          >
            {option.label}
          </Link>
        );
      })}
    </div>
  );
}

export const DEFAULT_RANGES = [
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
  { days: 365, label: "1y" },
] as const;

export const LONG_RANGES = [
  { days: 90, label: "90d" },
  { days: 365, label: "1y" },
  { days: 730, label: "2y" },
  { days: 3650, label: "All" },
] as const;

// -- formatting -------------------------------------------------------------

/**
 * Minutes as a person would say them.
 *
 * Sub-minute durations render in seconds rather than rounding to "0m". The
 * exercise library is full of them - a ten-second stretch is a real logged
 * session - and a table where every row read "0m" looked like a broken
 * duration field rather than a set of short clips.
 */
export function duration(minutes: number): string {
  if (minutes > 0 && minutes < 1) return `${Math.max(1, Math.round(minutes * 60))}s`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

/** One decimal, but only when there is one worth showing. */
export function num(value: number | null | undefined, places = 1): string {
  if (value === null || value === undefined) return "—";
  const rounded = Math.round(value * 10 ** places) / 10 ** places;
  return Number.isInteger(rounded) ? rounded.toLocaleString() : rounded.toFixed(places);
}

/**
 * A clock time in the zone that filed the entry.
 *
 * The timezone is not optional. A server component renders in UTC, and
 * formatting there turns a 7:36am coffee into a 9:36pm one the night before -
 * which is why `HealthDayOut` carries the zone at all. Locale is left to the
 * browser/runtime default rather than hardcoded, since this is a
 * general-audience self-hosted app.
 */
export function clock(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  });
}

export function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** Status colours, reserved for state and never reused as a series colour. */
export function band(
  value: number | null | undefined,
  good: number,
  poor: number,
  higherIsBetter = true,
): string {
  if (value === null || value === undefined) return "";
  const isGood = higherIsBetter ? value >= good : value <= good;
  const isPoor = higherIsBetter ? value < poor : value > poor;
  if (isGood) return "text-good";
  if (isPoor) return "text-critical";
  return "text-warning";
}
