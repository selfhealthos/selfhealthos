"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ApiError, apiGet, apiSend } from "@/lib/api/browser";
import type {
  FitnessExercise,
  FitnessPartner,
  FitnessPlaylistDetail,
  FitnessSession,
  FitnessStats,
} from "@/lib/api/types";

import { Card } from "../../ui";

/**
 * The player: one playlist, walked in a random order, one clip at a time.
 *
 * Everything here is client state on purpose - the current exercise, the
 * elapsed-time clock, and the running stats all change without a navigation,
 * which is exactly what a server component can't do. `Complete` is the only
 * thing that talks to the API mid-session; `Skip` just advances.
 *
 * `Focus` swaps the whole thing for a full-viewport view sized to be read
 * from across the room - see FocusView below.
 *
 * Ticking a friend sends their id with each Complete, and the backend writes
 * that clip to their log too. Who appears here is chosen in Settings, so a
 * long friends list doesn't turn into a long row of chips nobody trains with.
 */

function shuffled<T>(items: readonly T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const temp = out[i]!;
    out[i] = out[j]!;
    out[j] = temp;
  }
  return out;
}

function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function sessionDuration(seconds: number): string {
  return seconds < 60 ? "<1m" : `${Math.round(seconds / 60)}m`;
}

//: The three milestones the clock calls out mid-exercise, in seconds.
//: Nothing plays past 90s - a long hold just runs out the clock in silence.
const MILESTONES = [30, 60, 90] as const;

//: Where the tick marks survive a refresh. sessionStorage, not localStorage:
//: who you are training with is true for this session in this tab, and a
//: selection silently carried into next week's solo workout would log entries
//: to somebody who wasn't there. Keyed by playlist so two tabs don't collide.
function partnerStorageKey(playlistKey: string): string {
  return `selfhealthos:workout-partners:${playlistKey}`;
}

function readStoredPartners(playlistKey: string): string[] {
  try {
    const raw = sessionStorage.getItem(partnerStorageKey(playlistKey));
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    // Private mode, blocked site data, malformed JSON - none of which should
    // stop someone working out.
    return [];
  }
}

function ClipFrame({ exercise }: { exercise: FitnessExercise }) {
  return (
    <iframe
      key={exercise.video_id}
      className="size-full"
      // muted so autoplay isn't blocked by the browser, and looped
      // back to itself (YouTube's loop param needs playlist=<id> to
      // loop a single video rather than requiring an actual playlist)
      // - a 10-second mobility clip finishing mid-hold shouldn't go
      // to a blank frame.
      src={`https://www.youtube.com/embed/${exercise.video_id}?autoplay=1&rel=0&mute=1&loop=1&playlist=${exercise.video_id}`}
      title={exercise.title}
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowFullScreen
    />
  );
}

/**
 * Focus mode: the same session, sized to be read from a couple of metres away
 * while you're actually doing the exercise.
 *
 * A fixed overlay rather than a rearrangement of the page, so it covers the
 * app's top nav and sidebar too without this component knowing anything about
 * the layout around it. Everything that isn't the clip, the clock, or the two
 * buttons is dropped - the playlist header and recent sessions are things you
 * read before you start or after you finish, not mid-hold. The day totals and
 * the partner chips stay: both change what you do next.
 *
 * The clock is clamped rather than a fixed size: ~35mm of digit height is what
 * reads effortlessly at 2m, which is a different number of pixels on a laptop
 * than on a TV.
 *
 * Toggling moves the iframe to a different parent, so the clip remounts and
 * restarts. The elapsed clock lives in the parent and keeps counting; the clip
 * is a muted loop, so restarting it costs nothing worth a shared-player dance.
 */
function FocusView({
  exercise,
  elapsed,
  stats,
  pending,
  error,
  partners,
  withPartners,
  onTogglePartner,
  onComplete,
  onSkip,
  onExit,
}: {
  exercise: FitnessExercise;
  elapsed: number;
  stats: FitnessStats;
  pending: boolean;
  error: string | null;
  partners: FitnessPartner[];
  withPartners: string[];
  onTogglePartner: (id: string) => void;
  onComplete: () => void;
  onSkip: () => void;
  onExit: () => void;
}) {
  return (
    <div className="fixed inset-0 z-30 flex flex-col gap-4 bg-bg p-4 sm:p-6">
      <div className="flex shrink-0 items-center justify-end">
        <button
          type="button"
          onClick={onExit}
          className="rounded-md px-3 py-1.5 text-sm text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
        >
          Exit focus <span className="text-ink-muted">(Esc)</span>
        </button>
      </div>

      {/* Above the clip, not below it: this is the thing you walk back to the
          screen to press, and hunting for it under a 16:9 video means looking
          at the bottom of the screen instead of the exercise. Complete sits on
          the right, where the press that ends a set belongs. */}
      <div className="flex shrink-0 flex-col items-center gap-3">
        <div className="flex w-full max-w-3xl gap-4">
          <button
            type="button"
            onClick={onSkip}
            disabled={pending}
            className="flex-1 rounded-xl border border-border px-6 py-5 text-2xl font-semibold text-ink-dim transition-colors hover:bg-surface-2 disabled:opacity-60 sm:text-3xl"
          >
            Skip →
          </button>
          <button
            type="button"
            onClick={onComplete}
            disabled={pending}
            className="flex-1 rounded-xl bg-good px-6 py-5 text-2xl font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-60 sm:text-3xl"
          >
            ✓ Complete
          </button>
        </div>
        {/* Live here, not just a summary: a friend who taps out halfway gets
            unticked mid-session, and every Complete after that is yours
            alone. Leaving focus mode to reach the chips would mean the
            abandoned half of the workout lands in their log. */}
        {partners.length > 0 && (
          <div className="flex flex-wrap items-center justify-center gap-3">
            {partners.map((partner) => {
              const on = withPartners.includes(partner.id);
              return (
                <button
                  key={partner.id}
                  type="button"
                  aria-pressed={on}
                  disabled={!partner.accepts_partner_logging}
                  title={
                    partner.accepts_partner_logging
                      ? undefined
                      : `${partner.username} isn't accepting shared workouts`
                  }
                  onClick={() => onTogglePartner(partner.id)}
                  className={`rounded-full border px-5 py-2 text-lg transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                    on
                      ? "border-good bg-good/15 text-good"
                      : "border-border text-ink-dim hover:bg-surface-2"
                  }`}
                >
                  {on ? "✓ " : ""}
                  {partner.username}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 lg:flex-row lg:gap-10">
        <div className="aspect-video w-full max-w-4xl shrink-0 overflow-hidden rounded-xl bg-black lg:h-full lg:w-auto lg:max-w-[58%]">
          <ClipFrame exercise={exercise} />
        </div>

        <div className="shrink-0 text-center lg:text-left">
          <p className="text-2xl font-medium text-balance text-ink sm:text-3xl">
            {exercise.title}
          </p>
          <p className="text-[clamp(4rem,11vw,9rem)] leading-none font-bold tabular-nums text-ink">
            {clock(elapsed)}
          </p>
          {/* The running day totals, same numbers as the normal header's
              stats - they move on every Complete, including the presses made
              from in here. */}
          <div className="mt-6 flex justify-center gap-10 lg:justify-start">
            <div>
              <p className="text-4xl font-bold tabular-nums text-ink">
                {stats.minutes_today}
              </p>
              <p className="text-xs tracking-wider text-ink-muted uppercase">
                min today
              </p>
            </div>
            <div>
              <p className="text-4xl font-bold tabular-nums text-ink">
                {stats.completed_today}
              </p>
              <p className="text-xs tracking-wider text-ink-muted uppercase">
                exercises today
              </p>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="shrink-0 rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-center text-lg text-critical"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function playSound(ref: React.RefObject<HTMLAudioElement | null>) {
  const el = ref.current;
  if (!el) return;
  el.currentTime = 0;
  // Browsers can refuse an unprompted play() - a milestone that fires before
  // any click on the page is the one case that can hit this, and there's
  // nothing useful to do about it beyond not throwing.
  el.play().catch(() => {});
}

export function WorkoutPlayer({
  playlist,
  initialStats,
  initialRecent,
  partners,
}: {
  playlist: FitnessPlaylistDetail;
  initialStats: FitnessStats;
  initialRecent: FitnessSession[];
  partners: FitnessPartner[];
}) {
  const [order, setOrder] = useState<FitnessExercise[]>(() =>
    shuffled(playlist.exercises),
  );
  const [index, setIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [pending, setPending] = useState(false);
  const [stats, setStats] = useState(initialStats);
  const [recent, setRecent] = useState(initialRecent);
  const [withPartners, setWithPartners] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState(false);

  // Read after mount, not in a useState initialiser: sessionStorage doesn't
  // exist during the server render, and reading it there is a hydration
  // mismatch.
  //
  // Filtered against who is actually selectable right now, because the stored
  // ids can outlive the state they were saved in: a friend ticked earlier who
  // has since turned off shared workouts (or been unticked in Settings, or
  // removed) would otherwise stay selected behind a disabled chip nobody can
  // clear, and every Complete would fail with the same 409 forever.
  useEffect(() => {
    const selectable = new Set(
      partners.filter((p) => p.accepts_partner_logging).map((p) => p.id),
    );
    setWithPartners(
      readStoredPartners(playlist.key).filter((id) => selectable.has(id)),
    );
  }, [playlist.key, partners]);

  function togglePartner(id: string) {
    setWithPartners((current) => {
      const next = current.includes(id)
        ? current.filter((existing) => existing !== id)
        : [...current, id];
      try {
        sessionStorage.setItem(
          partnerStorageKey(playlist.key),
          JSON.stringify(next),
        );
      } catch {
        // Not being able to remember the selection across a refresh is a much
        // smaller problem than not being able to make one.
      }
      return next;
    });
  }

  // Escape leaves focus mode - it covers the whole viewport, and an overlay
  // with no keyboard way out is a trap for anyone not using a mouse.
  useEffect(() => {
    if (!focus) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFocus(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus]);

  const sound30 = useRef<HTMLAudioElement>(null);
  const sound60 = useRef<HTMLAudioElement>(null);
  const sound90 = useRef<HTMLAudioElement>(null);
  const soundCompleted = useRef<HTMLAudioElement>(null);
  const soundSkipped = useRef<HTMLAudioElement>(null);
  const milestoneRefs = { 30: sound30, 60: sound60, 90: sound90 } as const;

  const current = order[index];

  useEffect(() => {
    setElapsed(0);
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [index]);

  useEffect(() => {
    if ((MILESTONES as readonly number[]).includes(elapsed)) {
      playSound(milestoneRefs[elapsed as (typeof MILESTONES)[number]]);
    }
    // milestoneRefs is a fresh object every render but its ref contents are
    // stable - only `elapsed` should retrigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elapsed]);

  function advance() {
    if (index + 1 >= order.length) {
      setOrder(shuffled(playlist.exercises));
      setIndex(0);
    } else {
      setIndex(index + 1);
    }
  }

  async function complete() {
    if (!current || pending) return;
    setPending(true);
    setError(null);
    try {
      const updated = await apiSend<FitnessStats>("/fitness/complete", {
        method: "POST",
        body: {
          video_name: current.title,
          duration_s: elapsed,
          partner_ids: withPartners,
          // One id per press. The backend groups the rows it writes by this,
          // and a retry of the same press is recognisable rather than a
          // second session.
          coop_group_id: crypto.randomUUID(),
        },
      });
      if (updated) setStats(updated);
      apiGet<FitnessSession[]>("/fitness/recent")
        .then(setRecent)
        .catch(() => {});
      playSound(soundCompleted);
      advance();
    } catch (e) {
      // The backend refuses the whole press if any partner can't be logged
      // for, rather than quietly dropping them, so nothing was recorded and
      // the clip is still the current one. Say so instead of advancing.
      setError(
        e instanceof ApiError ? e.message : "Could not record that one.",
      );
    } finally {
      setPending(false);
    }
  }

  function skip() {
    if (pending) return;
    playSound(soundSkipped);
    advance();
  }

  if (!current) {
    return (
      <p className="text-sm text-ink-dim">This playlist has no exercises.</p>
    );
  }

  return (
    <div>
      {/* Preloaded, not rendered - these are cues, not media to look at. */}
      <audio ref={sound30} src="/audio/30seconds.mp3" preload="auto" />
      <audio ref={sound60} src="/audio/60seconds.mp3" preload="auto" />
      <audio ref={sound90} src="/audio/90seconds.mp3" preload="auto" />
      <audio ref={soundCompleted} src="/audio/completed.mp3" preload="auto" />
      <audio ref={soundSkipped} src="/audio/skipped.mp3" preload="auto" />

      {focus ? (
        <FocusView
          exercise={current}
          elapsed={elapsed}
          stats={stats}
          pending={pending}
          error={error}
          partners={partners}
          withPartners={withPartners}
          onTogglePartner={togglePartner}
          onComplete={complete}
          onSkip={skip}
          onExit={() => setFocus(false)}
        />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
            <div className="flex flex-wrap items-center gap-4">
              <Link
                href="/workout"
                aria-label="Back to playlists"
                className="flex size-8 items-center justify-center rounded-md text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
              >
                ‹
              </Link>
              <div>
                <p className="text-sm font-bold text-ink">{playlist.title}</p>
                <p className="text-xs text-ink-dim">
                  {playlist.exercises.length} exercises ·{" "}
                  {playlist.source_label}
                </p>
              </div>
              <div className="border-l border-border pl-4">
                <p className="text-xs text-ink-muted">Now playing</p>
                <p className="text-sm font-medium text-ink">{current.title}</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="text-center">
                <p className="text-sm font-bold tabular-nums text-ink">
                  {stats.minutes_today}
                </p>
                <p className="text-[10px] tracking-wide text-ink-muted uppercase">
                  min today
                </p>
              </div>
              <div className="text-center">
                <p className="text-sm font-bold tabular-nums text-ink">
                  {stats.completed_today}
                </p>
                <p className="text-[10px] tracking-wide text-ink-muted uppercase">
                  completed
                </p>
              </div>
              <p className="w-12 text-center text-lg font-bold tabular-nums text-ink">
                {clock(elapsed)}
              </p>
              <button
                type="button"
                onClick={complete}
                disabled={pending}
                className="rounded-md bg-good px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                ✓ Complete
              </button>
              <button
                type="button"
                onClick={skip}
                disabled={pending}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-ink-dim transition-colors hover:bg-surface-2 disabled:opacity-60"
              >
                Skip →
              </button>
              <button
                type="button"
                onClick={() => setFocus(true)}
                aria-label="Focus mode"
                title="Focus mode - big clock, readable across the room"
                className="flex size-8 items-center justify-center rounded-md border border-border text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="size-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.6}
                  aria-hidden
                >
                  <path
                    d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>

          {partners.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="text-xs tracking-wide text-ink-muted uppercase">
                Working out with
              </span>
              {partners.map((partner) => {
                const on = withPartners.includes(partner.id);
                return (
                  <button
                    key={partner.id}
                    type="button"
                    aria-pressed={on}
                    disabled={!partner.accepts_partner_logging}
                    title={
                      partner.accepts_partner_logging
                        ? undefined
                        : `${partner.username} isn't accepting shared workouts`
                    }
                    onClick={() => togglePartner(partner.id)}
                    className={`rounded-full border px-3 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                      on
                        ? "border-good bg-good/15 text-good"
                        : "border-border text-ink-dim hover:bg-surface-2"
                    }`}
                  >
                    {on ? "✓ " : ""}
                    {partner.username}
                  </button>
                );
              })}
              {withPartners.length > 0 && (
                <span className="text-xs text-ink-muted">
                  Each completed exercise is added to their log too.
                </span>
              )}
            </div>
          )}

          {error && (
            <p
              role="alert"
              className="mb-4 rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical"
            >
              {error}
            </p>
          )}

          <div className="lg:flex lg:gap-4">
            <div className="aspect-video flex-1 overflow-hidden rounded-xl bg-black">
              <ClipFrame exercise={current} />
            </div>

            <div className="mt-4 lg:mt-0 lg:w-72 lg:shrink-0">
              <Card title="Recent sessions">
                {recent.length === 0 ? (
                  <p className="text-sm text-ink-muted">No sessions yet.</p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {recent.map((session) => (
                      <li
                        key={session.id}
                        className="flex items-center justify-between gap-2"
                      >
                        <span className="min-w-0 flex-1 truncate text-ink">
                          {session.video_name}
                          {/* Whose press this was, when it wasn't yours. An entry
                            you don't remember doing is otherwise a mystery. */}
                          {session.logged_by && (
                            <span className="block text-xs text-ink-muted">
                              with {session.logged_by}
                            </span>
                          )}
                        </span>
                        <span className="shrink-0 text-xs tabular-nums text-ink-muted">
                          {sessionDuration(session.duration_s)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
