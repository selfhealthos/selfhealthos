"use client";

import { useState } from "react";

import { ApiError, apiGet, apiSend } from "@/lib/api/browser";
import type {
  SocialFriend,
  SocialRequestAck,
  SocialRequests,
  SocialSettings,
} from "@/lib/api/types";

import { Card } from "../ui";

/**
 * The friend graph, as three panels: add someone, answer who has asked, and
 * see who you know.
 *
 * All client state, because every action here changes the page without a
 * navigation. Each mutation refetches both lists rather than patching them
 * locally - accepting a request moves a row from one panel to the other, and
 * a friend can arrive from the other side while this page is open, so the
 * server's answer is the only one worth trusting.
 */

async function refresh(): Promise<[SocialFriend[], SocialRequests]> {
  return Promise.all([
    apiGet<SocialFriend[]>("/social/friends"),
    apiGet<SocialRequests>("/social/friend-requests"),
  ]);
}

function Avatar({ username, url }: { username: string; url?: string | null }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={url}
        alt=""
        className="size-8 shrink-0 rounded-full object-cover"
      />
    );
  }
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-semibold text-ink-dim">
      {username.slice(0, 2).toUpperCase()}
    </span>
  );
}

export function Friends({
  initialFriends,
  initialRequests,
  initialSettings,
}: {
  initialFriends: SocialFriend[];
  initialRequests: SocialRequests;
  initialSettings: SocialSettings;
}) {
  const [friends, setFriends] = useState(initialFriends);
  const [requests, setRequests] = useState(initialRequests);
  const [settings, setSettings] = useState(initialSettings);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function run(action: () => Promise<unknown>, message?: string) {
    setPending(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      const [nextFriends, nextRequests] = await refresh();
      setFriends(nextFriends);
      setRequests(nextRequests);
      if (message) setNotice(message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const value = query.trim();
    if (!value || pending) return;

    // A friend code is the fixed-length all-caps alphabet from the backend;
    // anything else is a username. Guessing wrong is harmless - the endpoint
    // takes both fields and matches exactly on whichever is set.
    const looksLikeCode = /^[ACDEFGHJKMNPQRTUVWXY34679]{10}$/i.test(value);
    const body = looksLikeCode ? { friend_code: value } : { username: value };

    setPending(true);
    setError(null);
    setNotice(null);
    try {
      const ack = await apiSend<SocialRequestAck>("/social/friend-requests", {
        body,
      });
      const [nextFriends, nextRequests] = await refresh();
      setFriends(nextFriends);
      setRequests(nextRequests);
      setQuery("");
      // The backend answers the same way for "no such user", "they don't want
      // to be found by username" and "they blocked you", so this message has
      // to cover all three without implying which. Saying "no such user"
      // would turn the form into a way to test who has an account here.
      setNotice(
        ack?.sent
          ? ack.state === "accepted"
            ? "You're now friends - they had already asked."
            : "Request sent."
          : "If that account exists and accepts requests, they'll see yours.",
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  const incoming = requests.incoming;
  const outgoing = requests.outgoing;

  return (
    <div className="space-y-6">
      {notice && (
        <p className="rounded-xl border border-border bg-surface-2 px-4 py-3 text-sm text-ink-dim">
          {notice}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical"
        >
          {error}
        </p>
      )}

      <Card
        title="Add a friend"
        subtitle="By username, or by the friend code they gave you."
      >
        <form onSubmit={add} className="flex flex-wrap gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="username or friend code"
            aria-label="Username or friend code"
            className="min-w-48 flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-muted"
          />
          <button
            type="submit"
            disabled={pending || !query.trim()}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            Send request
          </button>
        </form>

        <div className="mt-4 border-t border-border pt-4">
          <p className="text-xs tracking-wide text-ink-muted uppercase">
            Your friend code
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <code className="rounded-md bg-surface-2 px-2 py-1 font-mono text-sm tracking-widest text-ink">
              {settings.friend_code}
            </code>
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                run(async () => {
                  const next = await apiSend<SocialSettings>(
                    "/social/me/friend-code",
                  );
                  if (next) setSettings(next);
                }, "New friend code generated. The old one no longer works.")
              }
              className="text-xs text-ink-dim underline underline-offset-2 hover:text-ink"
            >
              Generate a new one
            </button>
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-ink-dim">
            <input
              type="checkbox"
              checked={settings.discoverable_by_username}
              disabled={pending}
              onChange={(e) =>
                run(async () => {
                  const next = await apiSend<SocialSettings>("/social/me", {
                    method: "PATCH",
                    body: { discoverable_by_username: e.target.checked },
                  });
                  if (next) setSettings(next);
                })
              }
            />
            Let people add me by username
          </label>
        </div>
      </Card>

      {incoming.length > 0 && (
        <Card title={`Requests (${incoming.length})`}>
          <ul className="space-y-2">
            {incoming.map((row) => (
              <li key={row.friendship_id} className="flex items-center gap-3">
                <Avatar
                  username={row.user.username}
                  url={row.user.avatar_url}
                />
                <span className="flex-1 truncate text-sm text-ink">
                  {row.user.username}
                </span>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() =>
                    run(
                      () =>
                        apiSend(
                          `/social/friend-requests/${row.friendship_id}/accept`,
                        ),
                      `You and ${row.user.username} are now friends.`,
                    )
                  }
                  className="rounded-md bg-good px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
                >
                  Accept
                </button>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() =>
                    run(() =>
                      apiSend(
                        `/social/friend-requests/${row.friendship_id}/decline`,
                      ),
                    )
                  }
                  className="rounded-md border border-border px-3 py-1.5 text-sm text-ink-dim transition-colors hover:bg-surface-2 disabled:opacity-60"
                >
                  Decline
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {outgoing.length > 0 && (
        <Card title="Sent" subtitle="Waiting for them to accept.">
          <ul className="space-y-2">
            {outgoing.map((row) => (
              <li key={row.friendship_id} className="flex items-center gap-3">
                <Avatar
                  username={row.user.username}
                  url={row.user.avatar_url}
                />
                <span className="flex-1 truncate text-sm text-ink-dim">
                  {row.user.username}
                </span>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() =>
                    run(() =>
                      apiSend(
                        `/social/friend-requests/${row.friendship_id}/cancel`,
                      ),
                    )
                  }
                  className="text-xs text-ink-muted underline underline-offset-2 hover:text-ink"
                >
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={`Friends (${friends.length})`}>
        {friends.length === 0 ? (
          <p className="text-sm text-ink-muted">
            Nobody yet. Send someone your friend code to get started.
          </p>
        ) : (
          <ul className="space-y-2">
            {friends.map((friend) => (
              <li
                key={friend.friendship_id}
                className="flex items-center gap-3"
              >
                <Avatar
                  username={friend.user.username}
                  url={friend.user.avatar_url}
                />
                <span className="flex-1 truncate text-sm text-ink">
                  {friend.user.username}
                </span>
                {friend.workout_partner && (
                  <span className="shrink-0 rounded-md bg-surface-2 px-2 py-0.5 text-[10px] tracking-wide text-ink-dim uppercase">
                    In workout picker
                  </span>
                )}
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => {
                    if (
                      !confirm(
                        `Remove ${friend.user.username}? Past workouts stay.`,
                      )
                    )
                      return;
                    void run(
                      () =>
                        apiSend(`/social/friends/${friend.user.id}`, {
                          method: "DELETE",
                        }),
                      `${friend.user.username} removed.`,
                    );
                  }}
                  className="text-xs text-ink-muted underline underline-offset-2 hover:text-critical"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
