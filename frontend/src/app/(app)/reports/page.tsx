import Link from "next/link";

import { PageHeader } from "../ui";

export const dynamic = "force-dynamic";

/**
 * Reports: a landing page for cross-cutting views over the Health dataset.
 *
 * Everywhere else, one page answers one question about one signal. A report
 * asks a question that only makes sense sliced across several - "what does
 * going into the office actually do to my body" needs steps, heart rate and
 * sleep all read through the same lens at once, which is a different shape
 * of page from the rest of this app and earns its own list rather than being
 * squeezed into the sidebar as more individual items.
 */

const REPORTS = [
  {
    href: "/reports/wfh",
    title: "Work From Home",
    description:
      "Every metric averaged by day type — WFH, office, weekend — so you can see what going in actually does to your body.",
  },
  {
    href: "/reports/seasons",
    title: "Seasons",
    description:
      "Every metric averaged by season — summer, autumn, winter, spring — so you can see how the time of year moves your body.",
  },
];

export default function ReportsPage() {
  return (
    <>
      <PageHeader title="Reports" subtitle="Cross-metric views, sliced a different way than the rest of the dashboard." />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {REPORTS.map((report) => (
          <Link
            key={report.href}
            href={report.href}
            className="rounded-xl border border-border bg-surface p-4 transition-colors hover:border-ink-muted hover:bg-surface-2"
          >
            <h2 className="text-sm font-bold text-ink">{report.title}</h2>
            <p className="mt-1 text-sm text-ink-dim">{report.description}</p>
          </Link>
        ))}
      </div>
    </>
  );
}
