"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { apiUpload } from "@/lib/api/browser";
import type { User } from "@/lib/api/types";

export function AvatarUpload({ user }: { user: User }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(user.avatar_url ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setPreview(URL.createObjectURL(file));
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("file", file);
      await apiUpload<User>("/auth/me/avatar", form);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload that photo");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-4">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="group relative size-20 shrink-0 overflow-hidden rounded-full border border-border bg-surface-2"
        aria-label="Change profile photo"
      >
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element -- user-uploaded, not an optimizable static asset
          <img src={preview} alt="" className="size-full object-cover" />
        ) : (
          <span className="flex size-full items-center justify-center text-2xl font-semibold text-ink-muted">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
        )}
        <span className="absolute inset-0 flex items-center justify-center bg-black/50 text-xs font-medium text-white opacity-0 transition-opacity group-hover:opacity-100">
          {busy ? "Uploading…" : "Change"}
        </span>
      </button>

      <div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          onChange={onChange}
          className="hidden"
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="rounded-lg border border-border px-3 py-1.5 text-sm text-ink transition hover:border-brand-blue disabled:opacity-40"
        >
          {busy ? "Uploading…" : "Upload a photo"}
        </button>
        {error && <p className="mt-2 text-xs text-critical">{error}</p>}
      </div>
    </div>
  );
}
