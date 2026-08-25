"use client";

import { useState } from "react";

/**
 * The whole report, selectable and one click from the clipboard - see
 * `settings/Tokens.tsx`'s `Copyable` for the pattern this borrows. A
 * `<textarea readOnly>` rather than a `<pre>`: this block runs to thousands
 * of characters, and a native scrollbar the person can drag is worth more
 * here than it was for a short token.
 */
export function CopyableMarkdown({ markdown }: { markdown: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused (permissions, non-HTTPS, etc). The
      // text is still fully selectable in the box either way.
      setCopied(false);
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-xs text-ink-muted">
          {markdown.length.toLocaleString()} characters
        </span>
        <button
          onClick={copy}
          className="rounded-md border border-border px-3 py-1 text-xs font-medium text-ink transition-colors hover:bg-surface-2"
        >
          {copied ? "Copied" : "Copy to clipboard"}
        </button>
      </div>
      <textarea
        readOnly
        value={markdown}
        // Clicking selects everything - the fastest path to the clipboard on
        // a phone, where a copy button that silently failed (see catch
        // above) leaves select-and-copy as the only way out.
        onClick={(e) => e.currentTarget.select()}
        className="h-[32rem] w-full resize-y rounded-lg border border-border bg-surface p-3 font-mono text-xs whitespace-pre-wrap text-ink"
      />
    </div>
  );
}
