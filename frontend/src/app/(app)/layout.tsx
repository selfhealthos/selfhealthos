import Image from "next/image";
import Link from "next/link";

import { serverGet } from "@/lib/api/server";
import type { User } from "@/lib/api/types";
import { SignOut } from "@/components/SignOut";
import { ThemeToggle } from "@/components/ThemeToggle";

import { HealthNav } from "./HealthNav";

/**
 * The authenticated app shell: a fixed sidebar and a wide content column.
 *
 * Health is the only app - this layout wraps everything except /login and
 * /signup (a separate route group), and `serverGet` redirects to /login on
 * 401, which is the whole of this app's auth gate.
 *
 * The sidebar collapses to a scrolling strip on small screens rather than a
 * hamburger and a backdrop - one fewer piece of state.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await serverGet<User>("/auth/me");

  return (
    <div className="lg:flex">
      <aside className="border-b border-border bg-surface lg:sticky lg:top-0 lg:h-screen lg:w-56 lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/logo-mark.png" alt="" width={20} height={24} />
            <span className="text-sm font-bold tracking-wide text-ink">
              SelfHealth
              <span className="bg-gradient-to-r from-brand-teal via-brand-blue to-brand-purple bg-clip-text text-transparent">
                OS
              </span>
            </span>
          </Link>
          <ThemeToggle />
        </div>

        <div className="p-2">
          <HealthNav />
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3">
          <SignOut username={user.username} />
          <div className="flex items-center gap-3 text-xs">
            <Link href="/profile" className="text-ink-dim hover:text-ink hover:underline">
              Profile
            </Link>
            <Link href="/settings" className="text-ink-dim hover:text-ink hover:underline">
              Settings
            </Link>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 px-4 py-5 sm:px-6">{children}</main>
    </div>
  );
}
