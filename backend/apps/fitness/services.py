"""Playlist reads and session stats for the workout player.

Recording a completion is not this app's logic - see `apps.health.services.
log_exercise`, called from `api.py`, and `ExerciseEntry`'s own docstring
("named after the video followed"). This module only reads that table back
for the player's own "today" counters and recent list.
"""

from __future__ import annotations

from django.utils import timezone as dj_timezone

from apps.health import timeutils
from apps.health.models import ExerciseEntry

from .playlists import PLAYLISTS, PLAYLISTS_BY_KEY, exercises_for


def list_playlists() -> list[dict]:
    return [
        {
            "key": p.key,
            "title": p.title,
            "source_label": p.source_label,
            "logged_as": p.logged_as,
            "exercise_count": len(exercises_for(p.key)),
        }
        for p in PLAYLISTS
    ]


def playlist_detail(key: str) -> dict | None:
    definition = PLAYLISTS_BY_KEY.get(key)
    if definition is None:
        return None
    return {
        "key": definition.key,
        "title": definition.title,
        "source_label": definition.source_label,
        "logged_as": definition.logged_as,
        "exercises": [
            {"video_id": e.video_id, "title": e.title, "duration_s": e.duration_s}
            for e in exercises_for(definition.key)
        ],
    }


def today_stats(user) -> dict:
    tz = timeutils.tz_for(user)
    today = timeutils.local_date_of(dj_timezone.now(), tz)
    rows = ExerciseEntry.objects.filter(
        created_by=user, deleted_at__isnull=True, local_date=today
    ).values_list("duration_s", flat=True)
    seconds = sum(rows)
    return {"minutes_today": round(seconds / 60), "completed_today": len(rows)}


def recent_sessions(user, *, limit: int = 10) -> list[dict]:
    rows = ExerciseEntry.objects.filter(created_by=user, deleted_at__isnull=True).order_by(
        "-occurred_at"
    )[: max(1, min(limit, 50))]
    return [
        {
            "id": row.id,
            "video_name": row.video_name,
            "duration_s": row.duration_s,
            "occurred_at": row.occurred_at,
        }
        for row in rows
    ]
