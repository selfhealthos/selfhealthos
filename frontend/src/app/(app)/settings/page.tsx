import { serverGet } from "@/lib/api/server";
import type {
  AccessToken,
  HealthConnection,
  SocialFriend,
  SocialSettings,
  TokenScope,
  User,
} from "@/lib/api/types";

import { Connections } from "./Connections";
import { Tokens } from "./Tokens";
import { WorkoutFriends } from "./WorkoutFriends";

export const dynamic = "force-dynamic";

// Per-user settings: profile, wearable connections, and access tokens (which
// double as the MCP install flow - see Tokens.tsx's IssuedPanel).

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ connected?: string; error?: string }>;
}) {
  const [user, connections, tokens, scopes, friends, social, params] =
    await Promise.all([
      serverGet<User>("/auth/me"),
      serverGet<HealthConnection[]>("/health/connections"),
      serverGet<AccessToken[]>("/tokens"),
      serverGet<TokenScope[]>("/tokens/scopes"),
      serverGet<SocialFriend[]>("/social/friends"),
      serverGet<SocialSettings>("/social/me"),
      searchParams,
    ]);

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Settings
        </h1>
        <p className="mt-1 text-sm text-ink-dim">
          Signed in as {user.username}
        </p>
      </header>

      {/* The OAuth callback redirects back here with the outcome in the query
          string, because a route handler has nowhere else to put it. */}
      {params.connected && (
        <p className="mb-6 rounded-xl border border-good/30 bg-good/10 px-4 py-3 text-sm text-good">
          {params.connected} is connected. Sync it from the dashboard.
        </p>
      )}
      {params.error && (
        <p
          role="alert"
          className="mb-6 rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical"
        >
          {params.error}
        </p>
      )}

      <Connections initial={connections} />
      <WorkoutFriends initialFriends={friends} initialSettings={social} />
      <Tokens initial={tokens} scopes={scopes} />
    </main>
  );
}
