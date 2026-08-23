import { serverGet } from "@/lib/api/server";
import type { User } from "@/lib/api/types";
import { AvatarUpload } from "@/components/AvatarUpload";

export const dynamic = "force-dynamic";

const SEX_LABEL: Record<string, string> = {
  female: "Female",
  male: "Male",
  other: "Other",
};

export default async function ProfilePage() {
  const user = await serverGet<User>("/auth/me");

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Profile</h1>
        <p className="mt-1 text-sm text-ink-dim">How you show up, and what we know about you.</p>
      </header>

      <section className="rounded-xl border border-border bg-surface p-6">
        <AvatarUpload user={user} />

        <dl className="mt-8 grid grid-cols-2 gap-x-4 gap-y-5 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-ink-dim">Username</dt>
            <dd className="mt-0.5 font-medium text-ink">{user.username}</dd>
          </div>
          <div>
            <dt className="text-ink-dim">Birth date</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {user.birth_date ? new Date(user.birth_date).toLocaleDateString() : "Not set"}
            </dd>
          </div>
          <div>
            <dt className="text-ink-dim">Sex</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {user.sex ? (SEX_LABEL[user.sex] ?? user.sex) : "Not set"}
            </dd>
          </div>
        </dl>

        <p className="mt-6 text-xs text-ink-muted">
          Birth date and sex personalise the age/sex-adjusted scoring bands (VO2max, heart rate)
          used on your dashboard.
        </p>
      </section>
    </main>
  );
}
