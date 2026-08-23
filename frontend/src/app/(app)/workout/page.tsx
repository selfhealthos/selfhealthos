import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { FitnessPlaylist } from "@/lib/api/types";

import { PageHeader } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Workout: pick a playlist, then walk it one clip at a time.
 *
 * The playlists themselves are fixed, curated exercise-video libraries, not
 * something built up here - see `apps/fitness/playlists.py`. This page is
 * just the picker; `/workout/[key]` is the player.
 */

//: Fixed per playlist, matching the app's existing brand/viz tokens rather
//: than inventing new colour - see the dataviz skill's "plug in a design
//: system" step.
const ACCENTS: Record<string, string> = {
  "opex-mobility": "var(--color-brand-teal)",
  darebee: "var(--viz-2)",
};

export default async function WorkoutPage() {
  const playlists = await serverGet<FitnessPlaylist[]>("/fitness/playlists");

  return (
    <>
      <PageHeader
        title="Workout"
        subtitle="Pick a playlist. Each one plays a random exercise from it, one after another."
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {playlists.map((playlist) => {
          const accent = ACCENTS[playlist.key] ?? "var(--viz-1)";
          return (
            <Link
              key={playlist.key}
              href={`/workout/${playlist.key}`}
              className="overflow-hidden rounded-xl border border-border bg-surface transition-colors hover:border-ink-muted hover:bg-surface-2"
            >
              <div className="h-1" style={{ backgroundColor: accent }} />
              <div className="p-4">
                <p
                  className="mb-1 text-xs font-semibold tracking-wide uppercase"
                  style={{ color: accent }}
                >
                  {playlist.source_label}
                </p>
                <h2 className="text-sm font-bold text-ink">{playlist.title}</h2>
                <p className="mt-1 text-xs text-ink-dim">
                  {playlist.exercise_count} exercises · logs as {playlist.logged_as}
                </p>
              </div>
            </Link>
          );
        })}
      </div>
    </>
  );
}
