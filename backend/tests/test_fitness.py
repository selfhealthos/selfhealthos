"""The workout player: static playlists, and logging a completed clip.

Completions reuse `apps.health`'s `ExerciseEntry`/`log_exercise` rather than
a fitness-owned table - the property worth pinning is that a `/fitness/
complete` call actually lands there (and so shows up wherever else
`ExerciseEntry` is read, like the Activity page's logged-sessions table),
not in some parallel record this app alone knows about.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.fitness.playlists import PLAYLISTS, exercises_for
from apps.health.models import ExerciseEntry

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    return User.objects.create_user(username="alex", password=PASSWORD)


@pytest.fixture
def client_for():
    def _make(user):
        client = Client()
        client.force_login(user)
        return client

    return _make


def test_playlists_report_their_real_exercise_counts(alex, client_for):
    response = client_for(alex).get("/api/v1/fitness/playlists")

    assert response.status_code == 200
    body = {row["key"]: row for row in response.json()}
    assert set(body) == {p.key for p in PLAYLISTS}
    for playlist in PLAYLISTS:
        assert body[playlist.key]["exercise_count"] == len(exercises_for(playlist.key))
        assert body[playlist.key]["logged_as"] == playlist.logged_as


def test_playlist_detail_lists_every_exercise(alex, client_for):
    response = client_for(alex).get("/api/v1/fitness/playlists/opex-mobility")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Exercise Library - Mobility"
    assert len(body["exercises"]) == len(exercises_for("opex-mobility"))
    first = body["exercises"][0]
    assert set(first) == {"video_id", "title", "duration_s"}


def test_an_unknown_playlist_is_404(alex, client_for):
    response = client_for(alex).get("/api/v1/fitness/playlists/does-not-exist")

    assert response.status_code == 404


def test_completing_a_clip_creates_an_exercise_entry(alex, client_for):
    response = client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps({"video_name": "Half Moon", "duration_s": 13}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"minutes_today": 0, "completed_today": 1}
    entry = ExerciseEntry.objects.get(created_by=alex)
    assert entry.video_name == "Half Moon"
    assert entry.duration_s == 13


def test_stats_count_only_todays_completions(alex, client_for):
    client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps({"video_name": "Half Moon", "duration_s": 90}),
        content_type="application/json",
    )
    client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps({"video_name": "Cat Cow", "duration_s": 30}),
        content_type="application/json",
    )

    response = client_for(alex).get("/api/v1/fitness/stats")

    assert response.status_code == 200
    assert response.json() == {"minutes_today": 2, "completed_today": 2}


def test_recent_sessions_are_newest_first(alex, client_for):
    client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps({"video_name": "Half Moon", "duration_s": 13}),
        content_type="application/json",
    )
    client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps({"video_name": "Cat Cow", "duration_s": 20}),
        content_type="application/json",
    )

    response = client_for(alex).get("/api/v1/fitness/recent")

    assert response.status_code == 200
    names = [row["video_name"] for row in response.json()]
    assert names == ["Cat Cow", "Half Moon"]


def test_a_second_users_completions_stay_separate(alex, client_for):
    sam = User.objects.create_user(username="sam", password=PASSWORD)
    client_for(sam).post(
        "/api/v1/fitness/complete",
        data=json.dumps({"video_name": "Half Moon", "duration_s": 13}),
        content_type="application/json",
    )

    response = client_for(alex).get("/api/v1/fitness/stats")

    assert response.status_code == 200
    assert response.json() == {"minutes_today": 0, "completed_today": 0}
