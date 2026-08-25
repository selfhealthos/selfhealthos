import { serverGet } from "@/lib/api/server";
import type { AccountTimezones, User } from "@/lib/api/types";
import { AvatarUpload } from "@/components/AvatarUpload";
import { TimezonePicker } from "@/components/TimezonePicker";

export const dynamic = "force-dynamic";

const SEX_LABEL: Record<string, string> = {
  female: "Female",
  male: "Male",
  other: "Other",
};

export default async function ProfilePage() {
  const [user, zones] = await Promise.all([
    serverGet<User>("/auth/me"),
    serverGet<AccountTimezones>("/auth/timezones"),
  ]);

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <header className="mb-8">
        <h1 className="text-ink text-2xl font-semibold tracking-tight">Profile</h1>
        <p className="text-ink-dim mt-1 text-sm">How you show up, and what we know about you.</p>
      </header>

      <section className="border-border bg-surface rounded-xl border p-6">
        <AvatarUpload user={user} />

        <dl className="mt-8 grid grid-cols-2 gap-x-4 gap-y-5 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-ink-dim">Username</dt>
            <dd className="text-ink mt-0.5 font-medium">{user.username}</dd>
          </div>
          <div>
            <dt className="text-ink-dim">Birth date</dt>
            <dd className="text-ink mt-0.5 font-medium">
              {user.birth_date ? new Date(user.birth_date).toLocaleDateString() : "Not set"}
            </dd>
          </div>
          <div>
            <dt className="text-ink-dim">Sex</dt>
            <dd className="text-ink mt-0.5 font-medium">
              {user.sex ? (SEX_LABEL[user.sex] ?? user.sex) : "Not set"}
            </dd>
          </div>
        </dl>

        <p className="text-ink-muted mt-6 text-xs">
          Birth date and sex personalise the age/sex-adjusted scoring bands (VO2max, heart rate)
          used on your dashboard.
        </p>
      </section>

      <section className="border-border bg-surface mt-6 rounded-xl border p-6">
        <h2 className="text-ink text-sm font-semibold">Where you are</h2>
        <p className="text-ink-dim mt-1 mb-4 text-sm">
          This decides which calendar day an entry belongs to. Every page that says
          &ldquo;today&rdquo; — the Body table, the entries timeline, your habit streaks — measures
          the day from here, and the day is stored when you save, so a wrong timezone can file this
          morning&apos;s weigh-in under a date those pages have not reached yet.
        </p>

        <TimezonePicker current={zones.current} timezones={zones.timezones} />
      </section>
    </main>
  );
}
