"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * The app's sidebar nav over the Health dataset - a dozen views over one
 * dataset, not one page, so a sidebar rather than a single centred column.
 *
 * Sections rather than a flat list: fifteen flat items is already at the
 * limit of what can be scanned.
 */

type Item = { href: string; label: string; icon: string };

const SECTIONS: ReadonlyArray<{ title: string; items: readonly Item[] }> = [
  {
    title: "Day",
    items: [
      { href: "/", label: "Today", icon: "●" },
      { href: "/trends", label: "Trends", icon: "▲" },
      { href: "/heatmap", label: "Heatmap", icon: "▩" },
    ],
  },
  {
    title: "Logged",
    items: [
      { href: "/habits", label: "Habits", icon: "✓" },
      { href: "/diet", label: "Diet", icon: "◆" },
      { href: "/gut", label: "Gut", icon: "◍" },
      { href: "/vitals", label: "BP + Weight", icon: "◔" },
      { href: "/body", label: "Body", icon: "◫" },
      { href: "/labs", label: "Labs", icon: "◇" },
      { href: "/notes", label: "Notes", icon: "✎" },
      { href: "/docs", label: "Docs", icon: "☰" },
      { href: "/office", label: "Office days", icon: "▦" },
    ],
  },
  {
    title: "Wearable",
    items: [
      { href: "/sleep", label: "Sleep", icon: "☾" },
      { href: "/heart", label: "Heart", icon: "♥" },
      { href: "/activity", label: "Activity", icon: "▪" },
    ],
  },
];

export function HealthNav() {
  const pathname = usePathname();

  return (
    <nav className="space-y-4">
      {SECTIONS.map((section) => (
        <div key={section.title}>
          <p className="px-3 pb-1 text-[10px] font-semibold tracking-wider text-ink-muted uppercase">
            {section.title}
          </p>
          <div className="space-y-0.5">
            {section.items.map((item) => {
              // Exact match for the index, prefix for the rest — "/" would
              // otherwise light up on every page.
              const active =
                item.href === "/"
                  ? pathname === "/" || pathname.startsWith("/day")
                  : pathname.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded px-3 py-1.5 text-sm transition-colors ${
                    active
                      ? "bg-surface-2 font-medium text-ink"
                      : "text-ink-dim hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  <span
                    className={`w-4 text-center text-xs ${active ? "text-brand-blue" : "text-ink-muted"}`}
                    aria-hidden
                  >
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
