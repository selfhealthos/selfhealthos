"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiSend } from "@/lib/api/browser";
import type { AccessToken, AccessTokenCreated, TokenScope } from "@/lib/api/types";

/**
 * Access tokens: the credential every non-browser client presents.
 *
 * The secret is shown exactly once, on creation, and there is no endpoint that
 * can show it again — the database holds only a hash. So the one-time panel is
 * the whole design problem here: it has to be impossible to miss, impossible
 * to dismiss by accident, and it has to hand over something directly usable
 * rather than a bare string the reader then has to work out what to do with.
 * Hence the ready-made `claude mcp add` line beside the raw token.
 *
 * Scopes are checkboxes driven by `/tokens/scopes` rather than a fixed list,
 * because the scope vocabulary lives in `apps/tokens/scopes.py` and a copy
 * here would drift the first time one is added. Only the default *selection*
 * is a UI decision.
 */

//: Preselected on a fresh form — read, not write. Anything that writes should
//: be a deliberate tick.
const DEFAULT_SCOPES = ["health:read"];

const KINDS = [
  { value: "agent", label: "Agent (Claude Code / MCP)" },
  { value: "device", label: "Device (phone, tablet)" },
  { value: "script", label: "Script" },
];

export function Tokens({
  initial,
  scopes,
}: {
  initial: AccessToken[];
  scopes: TokenScope[];
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("agent");
  const [chosen, setChosen] = useState<string[]>(DEFAULT_SCOPES);
  const [issued, setIssued] = useState<AccessTokenCreated | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (key: string) =>
    setChosen((current) =>
      current.includes(key) ? current.filter((s) => s !== key) : [...current, key],
    );

  async function create() {
    setError(null);
    // Validated on submit, not by greying out the button: a disabled control
    // absorbs the click and explains nothing.
    if (!name.trim()) {
      setError("Give the token a name — it is how you tell them apart when revoking one.");
      return;
    }
    if (chosen.length === 0) {
      setError("Choose at least one scope. A token with none can call nothing.");
      return;
    }

    setBusy(true);
    try {
      const created = await apiSend<AccessTokenCreated>("/tokens", {
        method: "POST",
        body: { name: name.trim(), kind, scopes: chosen },
      });
      setIssued(created);
      setName("");
      setChosen(DEFAULT_SCOPES);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(token: AccessToken) {
    setError(null);
    try {
      await apiSend(`/tokens/${token.id}`, { method: "DELETE" });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work");
    }
  }

  return (
    <section className="mt-10 space-y-4">
      <div>
        <h2 className="text-sm font-medium text-ink-dim">Access tokens</h2>
        <p className="mt-1 text-xs text-ink-dim">
          One credential per client. Anything that is not a browser — Claude Code over{" "}
          <code className="rounded bg-surface-2 px-1 py-0.5 font-mono">/mcp</code>, a script —
          presents one of these instead of signing in.
        </p>
      </div>

      {issued && <IssuedPanel token={issued} onDismiss={() => setIssued(null)} />}

      <div className="rounded-xl border border-border bg-surface p-5">
        <h3 className="mb-4 font-medium text-ink">New token</h3>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-ink-dim">
            Name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Claude Code (laptop)"
              className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-brand-blue"
            />
          </label>
          <label className="text-xs text-ink-dim">
            Kind
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-brand-blue"
            >
              {KINDS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="mt-4">
          <legend className="text-xs text-ink-dim">
            What it may do. A token cannot even <em>see</em> a tool outside its scopes.
          </legend>
          <div className="mt-2 space-y-1.5">
            {scopes.map((scope) => (
              <label key={scope.key} className="flex items-start gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={chosen.includes(scope.key)}
                  onChange={() => toggle(scope.key)}
                  className="mt-1"
                />
                <span>
                  {scope.label}
                  <span className="ml-2 text-xs text-ink-muted">{scope.description}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <button
          onClick={create}
          disabled={busy}
          className="mt-4 rounded-lg bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Creating…" : "Create token"}
        </button>

        {error && (
          <p role="alert" className="mt-3 text-sm text-critical">
            {error}
          </p>
        )}
      </div>

      <div className="rounded-xl border border-border bg-surface">
        {initial.length === 0 ? (
          <p className="p-5 text-sm text-ink-dim">No tokens yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {initial.map((token) => (
              <li key={token.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">
                    {token.name}
                    {!token.is_live && (
                      <span className="ml-2 text-xs font-normal text-ink-muted">
                        {token.revoked_at ? "revoked" : "expired"}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-dim">
                    <code className="font-mono">{token.masked}</code> · {token.scopes.join(", ")}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {token.last_used_at
                      ? `Last used ${new Date(token.last_used_at).toLocaleString()}`
                      : "Never used"}
                    {token.expires_at &&
                      ` · expires ${new Date(token.expires_at).toLocaleDateString()}`}
                  </p>
                </div>
                {token.is_live && (
                  <button
                    onClick={() => revoke(token)}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs text-ink transition hover:border-critical hover:text-critical"
                  >
                    Revoke
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/**
 * The one-time reveal, and the MCP install command with the fresh token
 * baked in — this is the moment the secret actually exists in the browser,
 * so it is also the moment to hand over a ready-to-paste command rather than
 * a bare string the reader has to work out what to do with.
 *
 * `window.location.origin` is safe here: this runs in the browser, so it is
 * the address the reader actually typed, which is the address their client
 * will have to reach too.
 */
function IssuedPanel({
  token,
  onDismiss,
}: {
  token: AccessTokenCreated;
  onDismiss: () => void;
}) {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const command = `claude mcp add --transport http selfhealthos ${origin}/mcp --header "Authorization: Bearer ${token.secret}" --scope local`;

  return (
    <div className="rounded-xl border border-good/30 bg-good/10 p-5">
      <h3 className="font-medium text-good">{token.name} — copy it now</h3>
      <p className="mt-1 text-xs text-good/90">
        This is the only time the token is shown. Nothing can retrieve it afterwards; if it is
        lost the answer is a new token, not a recovery path.
      </p>

      <Copyable label="Token" value={token.secret} />
      <Copyable label="Add it to Claude Code" value={command} />

      <button
        onClick={onDismiss}
        className="mt-4 rounded-lg border border-good/40 px-3 py-1.5 text-xs text-good transition hover:bg-good/10"
      >
        I have copied it
      </button>
    </div>
  );
}

function Copyable({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused. The text is selectable either way,
      // which is why it is rendered in full rather than truncated.
      setCopied(false);
    }
  }

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-good">{label}</span>
        <button
          onClick={copy}
          className="rounded-md border border-good/40 px-2 py-0.5 text-xs text-good transition hover:bg-good/10"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="mt-1 overflow-x-auto rounded-lg bg-surface p-3 text-xs break-all whitespace-pre-wrap select-all text-ink">
        {value}
      </pre>
    </div>
  );
}
