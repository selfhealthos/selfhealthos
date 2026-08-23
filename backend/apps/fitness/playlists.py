"""Curated exercise-video playlists.

Fixed, not user-editable - the two libraries here are the whole feature.
Each is a flat JSON file of `{id, title, duration}` in `data/`: `id` is a
YouTube video id, `duration` is the clip length in seconds. Loaded once and
cached, since these files never change at runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class Exercise:
    video_id: str
    title: str
    duration_s: int


@dataclass(frozen=True)
class PlaylistDef:
    key: str
    title: str
    source_label: str
    #: What completing a clip from this playlist is described as on the
    #: picker card, e.g. "stretch" or "workout". Not stored on the logged
    #: entry - `ExerciseEntry` has no category, and `video_name` alone is
    #: what the rest of the app already groups sessions by.
    logged_as: str
    data_file: str


PLAYLISTS: tuple[PlaylistDef, ...] = (
    PlaylistDef(
        key="opex-mobility",
        title="Exercise Library - Mobility",
        source_label="OPEX Fitness",
        logged_as="stretch",
        data_file="stretch.json",
    ),
    PlaylistDef(
        key="darebee",
        title="Exercise Library",
        source_label="Darebee",
        logged_as="workout",
        data_file="darebee.json",
    ),
)

PLAYLISTS_BY_KEY: dict[str, PlaylistDef] = {p.key: p for p in PLAYLISTS}


@cache
def exercises_for(key: str) -> tuple[Exercise, ...]:
    definition = PLAYLISTS_BY_KEY[key]
    raw = json.loads((DATA_DIR / definition.data_file).read_text())
    return tuple(
        Exercise(video_id=row["id"], title=row["title"], duration_s=int(row["duration"]))
        for row in raw
    )
