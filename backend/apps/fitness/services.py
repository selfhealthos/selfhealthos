"""Playlist reads, session stats, and the one orchestration this app owns.

Recording a completion is not this app's logic - `apps.health` owns what an
`ExerciseEntry` is, and `apps.social` owns who may write one to somebody
else's account. What lives here is the sequencing of those two, because the
workout player is the only caller that needs both.
"""

from __future__ import annotations

from django.utils import timezone as dj_timezone

from apps.health import services as health_services
from apps.health import timeutils
from apps.health.models import ExerciseEntry
from apps.social import services as social_services

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
    rows = (
        ExerciseEntry.objects.filter(created_by=user, deleted_at__isnull=True)
        .select_related("logged_by")
        .order_by("-occurred_at")[: max(1, min(limit, 50))]
    )
    return [
        {
            "id": row.id,
            "video_name": row.video_name,
            "duration_s": row.duration_s,
            "occurred_at": row.occurred_at,
            # Only when somebody else logged it. log_exercise sets logged_by
            # on solo rows too, so comparing ids is what distinguishes them.
            "logged_by": (
                row.logged_by.username
                if row.logged_by_id and row.logged_by_id != row.created_by_id
                else None
            ),
        }
        for row in rows
    ]


def available_partners(user) -> list[dict]:
    """The friends this user ticked for the picker, for the player to render.

    Reads `FriendPref.workout_partner`, which is a *display* filter. Whether
    any of them may actually be logged for is decided at completion time by
    `social_services.assert_can_log_for`, which deliberately ignores that flag.
    """
    return [
        {
            "id": friend.pk,
            "username": friend.username,
            "avatar_url": friend.avatar.url if friend.avatar else None,
            "accepts_partner_logging": friend.allow_partner_logging,
        }
        for friend in social_services.workout_partners(user)
    ]


def complete_exercise(
    user, *, video_name: str, duration_s: int, partner_ids=(), coop_group_id=None
) -> dict:
    """Finish one clip, for the user and anyone who trained with them.

    The permission question goes to `apps.social` and the writing goes to
    `apps.health`; the only thing decided here is that the first must happen
    before the second, and that a refused partner aborts the whole press.

    `assert_can_log_for` raises rather than filtering. A silently dropped
    partner would leave the person looking at a ticked name next to someone
    whose log never received the entry, which is worse than an error they can
    do something about.
    """
    partners = social_services.assert_can_log_for(user, list(partner_ids))
    health_services.log_shared_exercise(
        user,
        video_name=video_name,
        duration_s=duration_s,
        partners=partners,
        coop_group_id=coop_group_id,
    )
    return today_stats(user)
