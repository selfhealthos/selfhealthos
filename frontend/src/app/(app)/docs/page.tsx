import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { HealthDoc } from "@/lib/api/types";

import { Card, Empty, PageHeader, shortDate } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Docs: photographed documents — pathology results, scripts, referrals.
 *
 * A row appears whether or not its image does. `photo_path` in the archive is
 * an on-device path (`/storage/emulated/0/…`) that means nothing off the phone,
 * and `photo` stays null until the media backfill matches a file to the row —
 * but the date and the title are most of the value, and hiding the row until
 * the picture arrives would make a document that exists look like one that was
 * never taken.
 */

export default async function DocsPage() {
  const docs = await serverGet<HealthDoc[]>("/health/docs");
  const withImages = docs.filter((doc) => doc.image_url).length;

  return (
    <>
      <PageHeader
        title="Docs"
        subtitle={
          docs.length > 0
            ? `${docs.length} document${docs.length === 1 ? "" : "s"}, ${withImages} with a scan attached.`
            : undefined
        }
      />

      {docs.length === 0 ? (
        <Card>
          <Empty>No documents recorded. They arrive from the phone app.</Empty>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {docs.map((doc) => (
            <Card key={doc.id}>
              {doc.image_url ? (
                <a href={doc.image_url} target="_blank" rel="noreferrer">
                  {/* Plain <img>: these are user uploads of unknown dimensions
                      served from the same origin, so next/image's resizing
                      pipeline buys nothing and its width/height requirement is
                      a value we do not have. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={doc.image_url}
                    alt={doc.title || `Document from ${doc.local_date}`}
                    className="mb-3 max-h-64 w-full rounded-lg object-cover"
                  />
                </a>
              ) : (
                <div className="mb-3 flex h-32 items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-400 dark:bg-slate-800 dark:text-slate-600">
                  Scan not uploaded
                </div>
              )}
              <h2 className="text-sm font-medium">{doc.title || "Untitled"}</h2>
              <Link
                href={`/day/${doc.local_date}`}
                className="text-xs text-slate-400 hover:underline dark:text-slate-600"
              >
                {shortDate(doc.local_date)}
              </Link>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
