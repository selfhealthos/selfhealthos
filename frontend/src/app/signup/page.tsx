"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import { ThemeToggle } from "@/components/ThemeToggle";

export default function SignupPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [sex, setSex] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiSend("/auth/signup", {
        body: { username, password, birth_date: birthDate, sex },
      });
      // Full reload, not router.push - see login/page.tsx.
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create that account");
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center bg-bg px-6 py-12">
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
        <p className="mb-6 text-center text-sm text-ink-dim">
          Create your account. This is a self-hosted instance - there are no
          password rules, so pick whatever you'll remember.
        </p>

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
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand-blue"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="birth_date" className="block text-sm font-medium text-ink">
                Birth date
              </label>
              <input
                id="birth_date"
                type="date"
                required
                value={birthDate}
                onChange={(e) => setBirthDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand-blue"
              />
            </div>

            <div>
              <label htmlFor="sex" className="block text-sm font-medium text-ink">
                Sex
              </label>
              <select
                id="sex"
                value={sex}
                onChange={(e) => setSex(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand-blue"
              >
                <option value="">Prefer not to say</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>
          <p className="-mt-2 text-xs text-ink-muted">
            Used to personalise scoring bands (e.g. VO2max) on your dashboard.
          </p>

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
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-ink-dim">
          Already have an account?{" "}
          <Link href="/login" className="text-brand-blue underline underline-offset-2">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
