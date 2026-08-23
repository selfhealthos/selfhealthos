"""Celery entry points.

Thin by convention: the task owns queue routing and retry policy, `rollups.py`
owns the work.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


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


def _now():
    from django.utils import timezone

    return timezone.now()
