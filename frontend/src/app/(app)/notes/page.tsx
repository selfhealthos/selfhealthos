import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthNote } from "@/lib/api/types";

import { Card, clock, Empty, PageHeader, shortDate } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Notes: every diary entry, searchable.
 *
 * Ported from the dashboard's `notes.html`. The one thing that had to change is
 * the body: the Android app switched `content` from plain text to a JSON block
 * array partway through and never migrated the old rows, so half the archive
 * renders as `[{"t":"text","v":…}]` unless it is flattened first. That happens
 * in `services._note_body`, on the server, so the MCP tools see the same text
 * this page does.
 *
 * Each entry links to its day, because a note almost always makes sense next to
 * what was eaten and how the night before went.
 */

export default async function NotesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const search = (q ?? "").trim();

  const notes = await serverGet<HealthNote[]>(
    `/health/notes${search ? `?q=${encodeURIComponent(search)}` : ""}`,
  );
  const timeZone = "Australia/Melbourne";

  return (
    <>
      <PageHeader
        title="Notes"
        subtitle={`${notes.length} entr${notes.length === 1 ? "y" : "ies"}${search ? ` matching “${search}”` : ""}.`}
      />

      <form method="get" className="mb-4 flex gap-2">
        <input
          type="search"
          name="q"
          defaultValue={search}
          placeholder="Search titles and content…"
          aria-label="Search notes"
          className="w-full max-w-sm rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white dark:bg-slate-100 dark:text-slate-900"
        >
          Search
        </button>
        {search && (
          <Link
            href="/notes"
            className="self-center text-sm text-slate-500 hover:underline"
          >
            Clear
          </Link>
        )}
      </form>

      {notes.length === 0 ? (
        <Card>
          <Empty>
            {search ? `Nothing matching “${search}”.` : "No diary entries recorded."}
          </Empty>
        </Card>
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <Card key={note.id}>
              <article>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-sm font-semibold">{note.title || "Untitled"}</h2>
                  <Link
                    href={`/day/${note.local_date}`}
                    className="shrink-0 text-xs tabular-nums text-slate-400 hover:underline dark:text-slate-600"
                  >
                    {shortDate(note.local_date)} · {clock(note.at, timeZone)}
                  </Link>
                </div>
                {note.body && (
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">
                    {note.body}
                  </p>
                )}
              </article>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
