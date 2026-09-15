"use client";

/**
 * Save this report: as a PDF, or as a CSV.
 *
 * **PDF is the browser's own print-to-PDF, not a PDF library.** Every
 * mainstream browser's print dialog offers "Save as PDF" as a destination, and
 * a report page - a header, some stat tiles and a grid of small multiples - is
 * exactly the shape print CSS was designed for. The charts are inline SVG, so
 * they come out as vectors rather than a screenshot. The alternative is a
 * rendering dependency on one side or the other: a client-side PDF library
 * (which would rasterise the charts and re-implement the layout) or a
 * server-side one (which would need fonts, a headless renderer and a second
 * definition of this page). Neither earns its place against a stylesheet.
 *
 * **CSV is a real link, not a generated blob.** `/health/office/report.csv` is
 * an ordinary authenticated GET, so the same URL works from `curl` with a
 * `shos_pat_` token, the download survives JavaScript being off, and the
 * numbers come from the service rather than from whatever this component
 * happened to have in props.
 */

export function SaveAs({ days }: { days: number }) {
  // `days=0` is this page's "all time" sentinel and is stripped before the
  // API sees it, exactly as the page itself does when fetching.
  const csvHref = `/api/v1/health/office/report.csv${days ? `?days=${days}` : ""}`;

  return (
    <div className="flex items-center gap-2 print:hidden">
      <button
        type="button"
        onClick={() => window.print()}
        className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-ink transition hover:border-brand-blue"
      >
        Save as PDF
      </button>
      <a
        href={csvHref}
        // Not target="_blank": the response is an attachment, so the browser
        // downloads it and stays on this page. A new tab would open and
        // immediately close itself.
        download
        className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-ink transition hover:border-brand-blue"
      >
        Download CSV
      </a>
    </div>
  );
}
