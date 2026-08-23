"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { HealthAuthorize, HealthConnection } from "@/lib/api/types";

// Wearable connections. One card per provider, whether it is set up or not.
//
// The client secret is write-only: it is sent up and never read back, so this
// form always renders its field empty and leaving it blank keeps whatever is
// stored. There is no "show secret" affordance because there is nothing to
// show — the API cannot return it.

const SETUP_STEPS: Record<string, { url: string; steps: string[] }> = {
  fitbit: {
    url: "https://dev.fitbit.com/apps/new",
    steps: [
      'Register an app with type "Personal" — that is what grants intraday heart rate for your own account without applying to Fitbit for approval.',
      "Set the Redirect URL to exactly the callback shown below.",
      "Copy the OAuth 2.0 Client ID and Client Secret into this form.",
    ],
  },
};

export function Connections({ initial }: { initial: HealthConnection[] }) {
  return (
    <section className="space-y-4">
      <h2 className="text-sm font-medium text-ink-dim">Wearables</h2>
      {initial.map((connection) => (
        <ConnectionCard key={connection.provider} connection={connection} />
      ))}
    </section>
  );
}

function ConnectionCard({ connection }: { connection: HealthConnection }) {
  const router = useRouter();
  const [clientId, setClientId] = useState(connection.client_id ?? "");
  const [clientSecret, setClientSecret] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const help = SETUP_STEPS[connection.provider];
  // From the server, not from window.location: this is the exact string the
  // backend will send as redirect_uri, and Fitbit rejects anything that
  // differs by a character.
  const callback = connection.redirect_uri;

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError(null);
    setNote(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work");
    } finally {
      setBusy(null);
    }
  }

  const save = () =>
    run("save", async () => {
      // Validated here rather than by disabling the button. A disabled button
      // is indistinguishable from a broken one: it absorbs the click, says
      // nothing, and logs nothing anywhere.
      if (!clientId.trim()) {
        setError("Enter the OAuth 2.0 Client ID from your Fitbit app registration.");
        return;
      }
      if (!clientSecret.trim() && !connection.configured) {
        setError("Enter the Client Secret. It is only ever sent, never shown again.");
        return;
      }

      await apiSend(`/health/connections/${connection.provider}`, {
        method: "PUT",
        body: { client_id: clientId, client_secret: clientSecret },
      });
      setClientSecret("");
      setNote("Saved.");
      router.refresh();
    });

  const connect = () =>
    run("connect", async () => {
      const result = await apiSend<HealthAuthorize>(
        `/health/connections/${connection.provider}/authorize`,
      );
      // A full navigation, not router.push: the destination is fitbit.com.
      if (result?.authorize_url) window.location.href = result.authorize_url;
    });

  const disconnect = () =>
    run("disconnect", async () => {
      await apiSend(`/health/connections/${connection.provider}`, { method: "DELETE" });
      setNote("Disconnected. Your credentials are still saved.");
      router.refresh();
    });

  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium text-ink">{connection.label}</h3>
          <p className="mt-0.5 text-xs text-ink-dim">
            {connection.connected
              ? `Connected${connection.synced_through ? ` · synced through ${connection.synced_through}` : ""}`
              : connection.status === "expired"
                ? "Needs reconnecting"
                : connection.configured
                  ? "Credentials saved, not connected"
                  : "Not set up"}
          </p>
        </div>
        {connection.connected && (
          <span className="rounded-full bg-good/10 px-2 py-0.5 text-xs font-medium text-good ring-1 ring-inset ring-good/30">
            Connected
          </span>
        )}
      </div>

      {connection.last_sync_error && (
        <p className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          Last sync: {connection.last_sync_error}
        </p>
      )}

      {help && !connection.configured && (
        <ol className="mb-4 ml-4 list-decimal space-y-1 text-xs text-ink-dim marker:text-ink-muted">
          {help.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
          <li>
            <a
              href={help.url}
              target="_blank"
              rel="noreferrer"
              className="text-brand-blue underline underline-offset-2"
            >
              Register an app ↗
            </a>
          </li>
        </ol>
      )}

      {callback && (
        <p className="mb-4 text-xs text-ink-dim">
          Redirect URL to register:{" "}
          <code className="rounded bg-surface-2 px-1 py-0.5 font-mono">{callback}</code>
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-ink-dim">
          Client ID
          {/* No example value as a placeholder. A greyed "23ABCD" is one
              character away from a real Fitbit client ID and reads as an
              already-filled field. */}
          <input
            value={clientId}
            onChange={(event) => setClientId(event.target.value)}
            aria-label="OAuth 2.0 Client ID"
            className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 font-mono text-sm text-ink outline-none focus:border-brand-blue"
          />
        </label>
        <label className="text-xs text-ink-dim">
          Client secret
          <input
            type="password"
            value={clientSecret}
            onChange={(event) => setClientSecret(event.target.value)}
            autoComplete="off"
            placeholder={connection.configured ? "•••••••• (unchanged)" : ""}
            className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 font-mono text-sm text-ink outline-none focus:border-brand-blue"
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {/* Only ever disabled while a request is in flight. Anything else the
            click can explain for itself. */}
        <button
          onClick={save}
          disabled={busy !== null}
          className="rounded-lg bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy === "save" ? "Saving…" : "Save credentials"}
        </button>

        {connection.configured && !connection.connected && (
          <button
            onClick={connect}
            disabled={busy !== null}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-ink transition hover:border-brand-blue disabled:opacity-40"
          >
            {busy === "connect" ? "Redirecting…" : `Connect ${connection.label}`}
          </button>
        )}

        {connection.connected && (
          <button
            onClick={disconnect}
            disabled={busy !== null}
            className="rounded-lg border border-border px-4 py-2 text-sm text-ink transition hover:border-critical hover:text-critical disabled:opacity-40"
          >
            {busy === "disconnect" ? "Disconnecting…" : "Disconnect"}
          </button>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-critical">
          {error}
        </p>
      )}
      {note && <p className="mt-3 text-sm text-ink-dim">{note}</p>}
    </div>
  );
}
