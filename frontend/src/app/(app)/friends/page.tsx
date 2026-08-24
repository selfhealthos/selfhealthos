import { serverGet } from "@/lib/api/server";
import type {
  SocialFriend,
  SocialRequests,
  SocialSettings,
} from "@/lib/api/types";

import { Friends } from "./Friends";

export const dynamic = "force-dynamic";

// Managing the graph itself: who you know, who has asked, and how people find
// you. Which of those friends appear in the workout picker is a *display*
// setting and lives in Settings instead - see Settings' WorkoutFriends panel.

export default async function FriendsPage() {
  const [friends, requests, settings] = await Promise.all([
    serverGet<SocialFriend[]>("/social/friends"),
    serverGet<SocialRequests>("/social/friend-requests"),
    serverGet<SocialSettings>("/social/me"),
  ]);

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Friends
        </h1>
        <p className="mt-1 text-sm text-ink-dim">
          Add someone to log a workout you did together onto both your
          dashboards.
        </p>
      </header>

      <Friends
        initialFriends={friends}
        initialRequests={requests}
        initialSettings={settings}
      />
    </main>
  );
}
