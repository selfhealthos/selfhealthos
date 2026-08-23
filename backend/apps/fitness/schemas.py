from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ninja import Schema


class FitnessPlaylistOut(Schema):
    key: str
    title: str
    source_label: str
    logged_as: str
    exercise_count: int


class FitnessExerciseOut(Schema):
    video_id: str
    title: str
    duration_s: int


class FitnessPlaylistDetailOut(Schema):
    key: str
    title: str
    source_label: str
    logged_as: str
    exercises: list[FitnessExerciseOut]


class FitnessCompleteIn(Schema):
    video_name: str
    duration_s: int


class FitnessStatsOut(Schema):
    minutes_today: int
    completed_today: int


class FitnessSessionOut(Schema):
    id: UUID
    video_name: str
    duration_s: int
    occurred_at: datetime
