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
              {playlist.exercises.length} exercises · {playlist.source_label}
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
          <iframe
            key={current.video_id}
            className="size-full"
            // muted so autoplay isn't blocked by the browser, and looped
            // back to itself (YouTube's loop param needs playlist=<id> to
            // loop a single video rather than requiring an actual playlist)
            // - a 10-second mobility clip finishing mid-hold shouldn't go
            // to a blank frame.
            src={`https://www.youtube.com/embed/${current.video_id}?autoplay=1&rel=0&mute=1&loop=1&playlist=${current.video_id}`}
            title={current.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
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
    </div>
  );
}
