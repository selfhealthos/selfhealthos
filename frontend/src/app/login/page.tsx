"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import { ThemeToggle } from "@/components/ThemeToggle";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiSend("/auth/login", { body: { username, password } });
      // Full reload, not router.push: every page is a server component reading
      // the session cookie, and the router cache would serve the logged-out
      // render otherwise.
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center bg-bg px-6">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>

      <div className="mb-8 flex flex-col items-center gap-3">
        <Image src="/logo-mark.png" alt="" width={48} height={58} priority />
        <h1 className="text-xl font-bold tracking-tight text-ink">
          SelfHealth
          <span className="bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple bg-clip-text text-transparent">
            OS
          </span>
        </h1>
      </div>

      <div className="w-full max-w-sm">
        <p className="mb-6 text-center text-sm text-ink-dim">Sign in to continue.</p>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-ink">
              Username
            </label>
            <input
              id="username"
              type="text"
              required
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand-blue"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-ink">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand-blue"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-critical">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-ink-dim">
          New here?{" "}
          <Link href="/signup" className="text-brand-blue underline underline-offset-2">
            Create an account
          </Link>
        </p>
      </div>
    </main>
  );
}
