"""Pull a whole Withings history through the connected account.

    python manage.py backfill_withings --user yourusername --dry-run
    python manage.py backfill_withings --user yourusername

The ordinary sync is capped at `connections.MAX_SYNC_DAYS`, which is the right
window for "did this morning's weigh-in land yet" and useless for "I have been
standing on this scale since 2014". This walks the whole archive instead.

It costs almost nothing, which is why the cap is a UI concern rather than a
real constraint here: `getmeas` answers for an arbitrary range and pages at 500
measure groups, so a decade of daily weigh-ins is a handful of requests. That
is the opposite of Fitbit, where a long backfill is genuinely expensive and
`backfill_fitbit` exists to make it affordable.

Prefer this to `import_withings` when the account is connected. Both end up in
the same place, but the API carries a timezone on every measure group and a CSV
export carries none - so a history spanning a move between timezones is filed
correctly here and approximately there. Use `import_withings` when there is no
connection to pull through, or when you are working from an export of an
account you no longer have access to.

Idempotent, like every other path into these tables: readings are keyed on the
instant they were taken, so re-running adds nothing and a backfill overlapping
an already-synced period collapses into it.
"""

from __future__ import annotations

from datetime import time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as dj_timezone

from apps.accounts.models import User
from apps.health import rollups, timeutils
from apps.health.models import Connection
from apps.health.providers import withings

#: Far enough back to cover any Withings account - the first Withings scale
#: shipped in 2009. Bounded rather than open so the request carries a real
#: range, which the endpoint wants.
DEFAULT_DAYS = 365 * 20


class Command(BaseCommand):
    help = "Pull a full Withings measurement history through the connected account."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Username whose connection to use.")
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_DAYS,
            help="How far back to go, ending today. Defaults to everything.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and report, writing nothing.",
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {options['user']!r}.") from exc

        connection = Connection.objects.filter(
            user=user, provider=Connection.Provider.WITHINGS
        ).first()
        if connection is None or not connection.is_connected:
            raise CommandError(
                "That user has no connected Withings account. Connect it from "
                "Settings first, or use import_withings with a data export."
            )

        tz = timeutils.tz_for(user)
        end = dj_timezone.localdate()
        start = end - timedelta(days=max(1, options["days"]) - 1)

        until = timeutils.utc_from_local_parts(end, time(0, 0), tz) + timedelta(days=1)
        since = timeutils.utc_from_local_parts(start, time(0, 0), tz)

        report = withings.SyncReport(days_requested=(end - start).days + 1)
        self.stdout.write(f"Fetching {start} to {end} ...")

        with withings.Client(connection) as client:
            readings = withings.fetch_readings(
                client, since=since, until=until, fallback_tz=tz, report=report
            )
            report.requests = client.requests

        if report.stopped_early:
            self.stdout.write(self.style.WARNING(f"Stopped early: {report.stopped_early}"))
        for warning in report.warnings:
            self.stdout.write(self.style.WARNING(warning))

        if not readings:
            self.stdout.write(self.style.WARNING("Withings returned nothing for that range."))
            return

        readings.sort(key=lambda reading: reading.taken_at)
        self.stdout.write(
            f"{len(readings)} readings in {report.requests} request(s), "
            f"{readings[0].local_date} to {readings[-1].local_date}"
        )
        self._breakdown(readings)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run - nothing written."))
            return

        touched = withings.write_readings(user, readings, report)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nWrote {report.weight_entries} weight entries, "
                f"{report.body_measurements} body measurements, "
                f"{report.bp_entries} blood pressure readings "
                f"({report.duplicates_skipped} already held)."
            )
        )

        if touched:
            # Rebuilt over the span actually touched rather than the requested
            # window: a twenty-year request whose data starts in 2016 should not
            # walk seven thousand empty days.
            first, last = min(touched), max(touched)
            self.stdout.write(f"Rebuilding rollups for {first} to {last} ...")
            rollups.rebuild(user, first, last)
            self.stdout.write(self.style.SUCCESS("Done."))

    def _breakdown(self, readings) -> None:
        """What is actually in there, by year and by measurement.

        Printed before writing because it is the only chance to notice that a
        sensor stopped reporting years ago, which a single total hides.
        """
        counts: dict[int, int] = {}
        for reading in readings:
            counts[reading.local_date.year] = counts.get(reading.local_date.year, 0) + 1

        self.stdout.write("\n  by year:")
        for year in sorted(counts):
            self.stdout.write(f"    {year}  {counts[year]:>5}")

        for label, predicate in (
            ("weight", lambda r: r.weight_kg is not None),
            ("body fat", lambda r: r.fat_ratio_pct is not None or r.fat_mass_kg is not None),
            ("blood pressure", lambda r: r.systolic is not None and r.diastolic is not None),
        ):
            matching = [r for r in readings if predicate(r)]
            if matching:
                self.stdout.write(
                    f"  {label}: {len(matching)} readings, "
                    f"{matching[0].local_date} to {matching[-1].local_date}"
                )
            else:
                self.stdout.write(f"  {label}: none")
