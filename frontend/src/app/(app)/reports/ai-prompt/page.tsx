import { serverGet } from "@/lib/api/server";
import type { HealthAiReport } from "@/lib/api/types";

import { PageHeader, RangeTabs, shortDate } from "../../ui";
import { CopyableMarkdown } from "./CopyableMarkdown";

export const dynamic = "force-dynamic";

/**
 * AI Prompt Report: everything tracked, as one markdown document meant to be
 * pasted into a third-party chatbot - ChatGPT, Gemini, Claude, whichever -
 * for the person's own health insight. See `ai_report.py` on the backend for
 * what goes into it and why; this page is only the range picker and the
 * copy box.
 *
 * No LLM call happens here or on the backend. The design bet is that the
 * person is going to paste this somewhere external anyway, so the page's
 * only job is to make that paste as complete and unambiguous as possible.
 */

//: "All time" is `days=0` in the URL - a sentinel this page strips before
//: calling the API, where it means "no `days` param". Unlike the other
//: reports, "all time" is the *default* here: an AI asked for health
//: insight benefits from as much history as exists, not a recent slice.
const RANGES = [
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
  { days: 0, label: "All time" },
] as const;

export default async function AiPromptReportPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const requested = Number(raw);
  const current = RANGES.some((r) => r.days === requested) ? requested : 0;

  const report = await serverGet<HealthAiReport>(
    `/health/ai-report${current ? `?days=${current}` : ""}`,
  );

  return (
    <>
      <PageHeader
        title="AI Prompt Report"
        subtitle={`${shortDate(report.start)} – ${shortDate(report.end)}. Everything tracked, as one document ready to paste into an AI chat.`}
      >
        <RangeTabs basePath="/reports/ai-prompt" current={current} options={RANGES} />
      </PageHeader>

      <div className="space-y-3">
        <p className="text-xs text-ink-muted">
          This includes your medical history, medications and supplements if you&apos;ve
          recorded any in Settings → Profile. Review before pasting it anywhere you
          wouldn&apos;t otherwise share that with.
        </p>

        <CopyableMarkdown markdown={report.markdown} />
      </div>
    </>
  );
}
