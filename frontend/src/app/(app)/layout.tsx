import Image from "next/image";
import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { User } from "@/lib/api/types";
import { SignOut } from "@/components/SignOut";
import { ThemeToggle } from "@/components/ThemeToggle";

import { HealthNav } from "./HealthNav";

/**
 * The authenticated app shell: a full-width top nav, a sidebar below it, and
 * a wide content column.
 *
 * Health is the only app - this layout wraps everything except /login and
 * /signup (a separate route group), and `serverGet` redirects to /login on
 * 401, which is the whole of this app's auth gate.
 *
 * The sidebar collapses to a scrolling strip on small screens rather than a
 * hamburger and a backdrop - one fewer piece of state. The top nav's height
 * (h-14) is repeated in the sidebar's sticky offset below so the two don't
 * overlap once the page scrolls.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await serverGet<User>("/auth/me");

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-surface px-4">
        <Link href="/" className="flex items-center gap-2">
          <Image src="/logo-mark.png" alt="" width={20} height={24} />
          <span className="text-sm font-bold tracking-wide text-ink">
            SelfHealth
            <span className="bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple bg-clip-text text-transparent">
              OS
            </span>
          </span>
        </Link>

        <div className="flex items-center gap-3">
          <SignOut username={user.username} />

          <Link
            href="/profile"
            aria-label="Profile"
            title="Profile"
            className="flex size-7 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth={1.6}>
              <circle cx="12" cy="8" r="3.2" />
              <path
                d="M5 20c1.2-4 4-6 7-6s5.8 2 7 6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>

          <Link
            href="/settings"
            aria-label="Settings"
            title="Settings"
            className="flex size-7 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth={1.6}>
              <circle cx="12" cy="12" r="3" />
              <path
                d="M12 4.5v2M12 17.5v2M19.5 12h-2M6.5 12h-2M17.5 6.5l-1.4 1.4M7.9 16.1l-1.4 1.4M17.5 17.5l-1.4-1.4M7.9 7.9L6.5 6.5"
                strokeLinecap="round"
              />
            </svg>
          </Link>

          <ThemeToggle />
        </div>
      </header>

      <div className="lg:flex lg:flex-1">
        <aside className="border-b border-border bg-surface lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:w-56 lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-b-0">
          <div className="p-2">
            <HealthNav />
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
