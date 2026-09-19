"""Celery entry points.

Thin by convention: the task owns queue routing and retry policy, `rollups.py`
owns the work.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from celery import shared_task

logger = logging.getLogger(__name__)

#: How long the rollup waits behind the syncs it is meant to summarise. A
#: Fitbit pull is ~90 round trips; rebuilding before it lands produces metrics
#: for data that has not arrived yet.
SYNC_ROLLUP_DELAY_S = 20 * 60


@shared_task(name="health.rebuild_daily_metrics", queue="celery", ignore_result=True)
def rebuild_daily_metrics(user_pk: str, start: str | None = None, end: str | None = None) -> int:
    """Recompute derived daily metrics for one user.

    Defaults to the last week, which is the window an overnight run needs: a
    Fitbit backfill or a late phone sync can change a day that has already
    passed, and recomputing seven days costs nothing.
    """
    from apps.accounts.models import User

    from . import rollups, timeutils

    user = User.objects.get(pk=user_pk)
    today = timeutils.local_date_of(_now(), timeutils.tz_for(user))
    first = date.fromisoformat(start) if start else today - timedelta(days=6)
    last = date.fromisoformat(end) if end else today

    written = rollups.rebuild(user, first, last)
    logger.info("rebuilt %d daily metrics for %s (%s..%s)", written, user, first, last)
    return written


@shared_task(
    name="health.sync_connection",
    queue="celery",
    # The general queue, not `llm`: this is HTTP and database work with no
    # model call in it, and queueing a Fitbit pull behind a chat turn would be
    # a pointless wait.
    soft_time_limit=1_800,
    time_limit=1_860,
    ignore_result=True,
    # No automatic retry. A failure here is a dead grant, a wrong secret or a
    # rate limit, and none of the three is improved by trying again straight
    # away - the reason is written to the connection row for the person to see.
    max_retries=0,
)
def sync_connection(connection_pk: str, days: int | None = None) -> dict:
    from . import connections

    report = connections.run_sync(connection_pk, days=days)
    logger.info("connection %s sync finished: %s", connection_pk, report)
    return report


@shared_task(name="health.sync_due_connections", queue="celery", ignore_result=True)
def sync_due_connections() -> int:
    """Fan out a sync to every live connection, and rebuild what it changed.

    This is the thing that makes "connect Fitbit once and forget about it"
    true. Without it a connection only ever syncs when someone presses Sync
    now or completes the OAuth dance, so the data quietly stops on the day
    the account was linked and nothing anywhere reports a problem: the row
    still says `connected`, with no error, because no sync ran to fail.

    Expired grants are skipped rather than retried - they need the person to
    reconnect, and hammering a dead grant hourly just burns rate limit.
    """
    from .models import Connection

    due = Connection.objects.filter(status=Connection.Status.CONNECTED).values_list("pk", "user_id")
    users = set()
    for pk, user_id in due:
        sync_connection.delay(str(pk))
        users.add(user_id)

    # Chained separately rather than inside `sync_connection`: a user with two
    # providers should have their metrics rebuilt once, after both have run,
    # and the rollup is cheap enough that a fixed delay beats orchestration.
    for user_id in users:
        rebuild_daily_metrics.apply_async(args=[str(user_id)], countdown=SYNC_ROLLUP_DELAY_S)

    logger.info("queued %d connection syncs for %d users", len(due), len(users))
    return len(due)


def _now():
    from django.utils import timezone

    return timezone.now()
