"""Backfill Fitbit history through the date-range endpoints.

    python manage.py backfill_fitbit --user yourusername --days 120

Everything here was available at Fitbit all along. The problem it solves is
cost: `sync` walks one day at a time and spends about fourteen requests on
each, against a limit of 150 an hour. Three months that way is over a thousand
requests - days of pressing Sync, which is why an archive ends up with resting
heart rate on some days, breathing rate on a handful, and nothing on the rest.

Every endpoint used here also answers for a *range*, so the same three months
costs about thirty requests:

  * sleep logs with their stage segments - 100 nights per request
  * overnight SpO2 minutes - 30 days per request
  * HRV, breathing rate, SpO2 summary, skin temperature, cardio score - 30 days
  * resting heart rate and zone minutes - a year
  * steps, distance, floors, calories, active minutes - the whole window, one
    request each

What it does *not* backfill is intraday samples: minute-level heart rate has no
range form at all and still arrives one day at a time through the ordinary
sync. Everything a chart of daily values needs is here.

Idempotent throughout: sleep merges on Fitbit's log id, segments are replaced
per session, samples and daily metrics upsert on their natural keys. Re-running
after a rate limit picks up where it stopped.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.health.models import Connection
from apps.health.providers import fitbit


class Command(BaseCommand):
    help = "Backfill Fitbit sleep, SpO2 and daily metrics through the range endpoints."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Username of the user to backfill.")
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="How far back to go, ending today. Default 90.",
        )
        parser.add_argument(
            "--only",
            choices=["sleep", "daily"],
            help="Restrict to one half: the hypnograms and SpO2 minutes, or the daily numbers.",
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user with username {options['user']!r}") from exc

        connection = Connection.objects.filter(user=user, provider="fitbit").first()
        if connection is None:
            raise CommandError("That user has no Fitbit connection.")

        days = max(1, options["days"])
        end = date.today()
        start = end - timedelta(days=days - 1)
        only = options["only"]

        self.stdout.write(f"Backfilling {start} to {end} for {user.username}…")
        requests = 0
        stopped = ""

        if only != "daily":
            report = fitbit.backfill_detail(connection, start=start, end=end)
            requests += report.requests
            stopped = stopped or report.stopped_early
            self.stdout.write(
                f"  sleep: {report.sleep_sessions} logs, "
                f"{report.samples_written} SpO2 samples, {report.requests} requests"
            )

        if only != "sleep" and not stopped:
            report = fitbit.backfill_daily(connection, start=start, end=end)
            requests += report.requests
            stopped = stopped or report.stopped_early
            self.stdout.write(
                f"  daily: {report.daily_metrics_written} values, {report.requests} requests"
            )

        self.stdout.write(self.style.SUCCESS(f"Done in {requests} requests."))
        if stopped:
            # Not a failure: everything written stays written and the endpoints
            # are idempotent, so the answer is to run it again in an hour.
            self.stdout.write(self.style.WARNING(f"Stopped early: {stopped}"))
