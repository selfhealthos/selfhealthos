"""REST surface for the workout player.

Thin, like every other router: the playlists themselves are static config
(`playlists.py`), and the one thing with real logic - recording a completed
clip - is `apps.health`'s `log_exercise`, called here rather than
reimplemented, so this can't drift from what the phone sync and the MCP
tools already agree an exercise session is.
"""

from __future__ import annotations

from ninja import Router

from apps.core.exceptions import NotFound

from . import services
from .schemas import (
    FitnessCompleteIn,
    FitnessPartnerOut,
    FitnessPlaylistDetailOut,
    FitnessPlaylistOut,
    FitnessSessionOut,
    FitnessStatsOut,
)

router = Router(tags=["fitness"])


@router.get(
    "/playlists",
    response=list[FitnessPlaylistOut],
    summary="The fixed exercise-video libraries",
    operation_id="listFitnessPlaylists",
)
def list_playlists(request):
    return services.list_playlists()


@router.get(
    "/playlists/{key}",
    response=FitnessPlaylistDetailOut,
    summary="One playlist's exercises",
    operation_id="getFitnessPlaylist",
)
def get_playlist(request, key: str):
    detail = services.playlist_detail(key)
    if detail is None:
        raise NotFound(f"{key!r} is not a known playlist")
    return detail


@router.get(
    "/stats",
    response=FitnessStatsOut,
    summary="Minutes and clips completed today",
    operation_id="getFitnessStats",
)
def get_stats(request):
    return services.today_stats(request.auth)


@router.get(
    "/recent",
    response=list[FitnessSessionOut],
    summary="Recently completed exercise clips",
    operation_id="listFitnessRecent",
)
def get_recent(request, limit: int = 10):
    return services.recent_sessions(request.auth, limit=limit)


@router.get(
    "/partners",
    response=list[FitnessPartnerOut],
    summary="Friends you picked to show in the workout player",
    operation_id="listFitnessPartners",
)
def get_partners(request):
    return services.available_partners(request.auth)


@router.post(
    "/complete",
    response=FitnessStatsOut,
    summary="Record one completed exercise clip, optionally for friends too",
    operation_id="completeFitnessExercise",
)
def complete_exercise(request, payload: FitnessCompleteIn):
    return services.complete_exercise(
        request.auth,
        video_name=payload.video_name,
        duration_s=payload.duration_s,
        partner_ids=payload.partner_ids,
        coop_group_id=payload.coop_group_id,
    )
