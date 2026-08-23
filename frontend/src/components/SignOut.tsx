"use client";

import { apiSend } from "@/lib/api/browser";

export function SignOut({ username }: { username: string }) {
  async function signOut() {
    try {
      await apiSend("/auth/logout");
    } finally {
      // Hard navigation: every page is a server component reading the session
      // cookie, so the router cache would otherwise serve a logged-in render.
      window.location.href = "/login";
    }
  }

  return (
    <span className="text-xs text-ink-muted">
      {username}
      {" · "}
      <button onClick={signOut} className="underline underline-offset-2 hover:text-ink">
        Sign out
      </button>
    </span>
  );
}
