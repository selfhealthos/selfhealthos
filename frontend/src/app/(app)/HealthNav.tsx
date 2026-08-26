"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useNavCollapsed } from "./navCollapse";

/**
 * The app's sidebar nav over the Health dataset - a dozen views over one
 * dataset, not one page, so a sidebar rather than a single centred column.
 *
 * Sections rather than a flat list: fifteen flat items is already at the
 * limit of what can be scanned.
 *
 * Collapsed (the `lg:nav-collapsed:` classes below), it becomes an icon-only
 * rail: labels and section headings drop out, the icons stay put, and each
 * link picks up a tooltip since the icon alone doesn't name the page.
 */

type Item = { href: string; label: string; icon: string };

const SECTIONS: ReadonlyArray<{ title: string; items: readonly Item[] }> = [
  {
    title: "Day",
    items: [
      { href: "/entries", label: "Entries", icon: "▤" },
      { href: "/", label: "Today", icon: "●" },
      { href: "/trends", label: "Trends", icon: "▲" },
      { href: "/heatmap", label: "Heatmap", icon: "▩" },
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
  {
    title: "Fitness",
    items: [
      { href: "/gym", label: "Gym", icon: "▮" },
      { href: "/workout", label: "Workout", icon: "◈" },
      { href: "/fitness", label: "Tests", icon: "◎" },
      { href: "/friends", label: "Friends", icon: "◉" },
    ],
  },
  {
    title: "Logged",
    items: [
      { href: "/habits", label: "Habits", icon: "✓" },
      { href: "/diet", label: "Diet", icon: "◆" },
      { href: "/gut", label: "Gut", icon: "◍" },
      { href: "/blood-pressure", label: "Blood pressure", icon: "◔" },
      { href: "/body", label: "Body", icon: "◫" },
      { href: "/labs", label: "Labs", icon: "◇" },
      { href: "/notes", label: "Notes", icon: "✎" },
      { href: "/docs", label: "Docs", icon: "☰" },
      { href: "/wfh", label: "WFH", icon: "▧" },
      { href: "/reports", label: "Reports", icon: "▦" },
    ],
  },
];

export function HealthNav() {
  const pathname = usePathname();
  const collapsed = useNavCollapsed();

  return (
    <nav className="space-y-4">
      {SECTIONS.map((section) => (
        <div key={section.title}>
          <p className="px-3 pb-1 text-[10px] font-semibold tracking-wider text-ink-muted uppercase lg:nav-collapsed:hidden">
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
                  title={collapsed ? item.label : undefined}
                  className={`flex items-center gap-2.5 rounded px-3 py-1.5 text-sm transition-colors lg:nav-collapsed:justify-center lg:nav-collapsed:px-0 ${
                    active
                      ? "bg-surface-2 font-medium text-ink"
                      : "text-ink-dim hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  <span
                    className={`w-4 shrink-0 text-center text-xs ${active ? "text-brand-blue" : "text-ink-muted"}`}
                    aria-hidden
                  >
                    {item.icon}
                  </span>
                  <span className="lg:nav-collapsed:hidden">{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
