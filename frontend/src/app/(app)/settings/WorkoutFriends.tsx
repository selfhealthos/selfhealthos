"use client";

import Link from "next/link";
import { useState } from "react";

import { ApiError, apiSend } from "@/lib/api/browser";
import type { SocialFriend, SocialSettings } from "@/lib/api/types";

import { Card } from "../ui";

/**
 * Which friends appear in the workout player's picker.
 *
 * Two switches sit in this panel and they are easy to conflate, so the copy
 * says which is which in as many words:
 *
 *   - The per-friend checkbox is *display*. You might have ten friends and
 *     ever work out with one; this keeps the other nine out of the way.
 *   - "Let friends add shared workouts to my log" is the *permission*.
 *
 * Unticking someone here does not stop them logging a workout to you. A
 * checkbox that reads as a privacy control but isn't is worse than no
 * checkbox, which is why the permission is rendered first and the list below
 * it is explicitly labelled as not one.
 */
export function WorkoutFriends({
  initialFriends,
  initialSettings,
}: {
  initialFriends: SocialFriend[];
  initialSettings: SocialSettings;
}) {
  const [friends, setFriends] = useState(initialFriends);
  const [settings, setSettings] = useState(initialSettings);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  async function toggle(friend: SocialFriend, workoutPartner: boolean) {
    setPending(friend.user.id);
    setError(null);
    try {
      const updated = await apiSend<SocialFriend>(
        `/social/friends/${friend.user.id}/prefs`,
        {
          method: "PATCH",
          body: { workout_partner: workoutPartner },
        },
      );
      if (updated) {
        setFriends((rows) =>
          rows.map((r) => (r.user.id === updated.user.id ? updated : r)),
        );
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setPending(null);
    }
  }

  async function setPermission(allow: boolean) {
    setPending("me");
    setError(null);
    try {
      const next = await apiSend<SocialSettings>("/social/me", {
        method: "PATCH",
        body: { allow_partner_logging: allow },
      });
      if (next) setSettings(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setPending(null);
    }
  }

  return (
    <Card
      title="Working out with friends"
      subtitle="Finish an exercise together and it lands on both dashboards."
      className="mb-6"
    >
      {error && (
        <p role="alert" className="mb-3 text-sm text-critical">
          {error}
        </p>
      )}

      <label className="flex items-start gap-3">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.allow_partner_logging}
          disabled={pending === "me"}
          onChange={(e) => void setPermission(e.target.checked)}
        />
        <span className="text-sm">
          <span className="text-ink">
            Let my friends add shared workouts to my log
          </span>
          <span className="mt-0.5 block text-xs text-ink-muted">
            Entries are labelled with who added them, and you can delete any of
            them. Turning this off means nobody can write to your log but you.
          </span>
        </span>
      </label>

      <div className="mt-4 border-t border-border pt-4">
        <p className="text-xs tracking-wide text-ink-muted uppercase">
          Show in my workout picker
        </p>
        <p className="mt-1 mb-3 text-xs text-ink-muted">
          Just tidies the player down to the people you actually train with. It
          doesn&apos;t change who can add workouts to your log — that&apos;s the
          setting above.
        </p>

        {friends.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No friends yet.{" "}
            <Link
              href="/friends"
              className="underline underline-offset-2 hover:text-ink"
            >
              Add one
            </Link>
            .
          </p>
        ) : (
          <ul className="space-y-2">
            {friends.map((friend) => (
              <li key={friend.friendship_id}>
                <label className="flex items-center gap-3 text-sm">
                  <input
                    type="checkbox"
                    checked={friend.workout_partner}
                    disabled={pending === friend.user.id}
                    onChange={(e) => void toggle(friend, e.target.checked)}
                  />
                  <span className="flex-1 truncate text-ink">
                    {friend.user.username}
                  </span>
                  {!friend.accepts_partner_logging && (
                    // Rendered rather than hidden: a name silently missing from
                    // the picker reads as a bug, and this is the friend's own
                    // choice, not something the owner of this page can change.
                    <span className="shrink-0 text-xs text-ink-muted">
                      not accepting shared workouts
                    </span>
                  )}
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
