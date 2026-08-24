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


# --------------------------------------------------------------------------
# Working out with a friend
# --------------------------------------------------------------------------


@pytest.fixture
def blake(db):
    return User.objects.create_user(username="blake", password=PASSWORD)


def befriend(a, b):
    from apps.social import services as social

    social.send_request(a, username=b.username)
    social.accept_request(b, social.get_friendship(a, b).pk)


def test_completing_with_a_partner_lands_on_both_dashboards(alex, blake, client_for):
    befriend(alex, blake)

    response = client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps(
            {"video_name": "Deep Squat Hold", "duration_s": 120, "partner_ids": [str(blake.pk)]}
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["completed_today"] == 1
    assert ExerciseEntry.objects.filter(created_by=blake).count() == 1
    # And on blake's own player, without blake having done anything.
    assert client_for(blake).get("/api/v1/fitness/stats").json()["completed_today"] == 1


def test_a_non_friend_is_refused_and_nothing_is_written(alex, blake, client_for):
    response = client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps(
            {"video_name": "Deep Squat Hold", "duration_s": 120, "partner_ids": [str(blake.pk)]}
        ),
        content_type="application/json",
    )

    assert response.status_code == 409
    # Not even the caller's own row: a refused partner aborts the whole press,
    # so the session can be retried without double-logging the presser.
    assert ExerciseEntry.objects.count() == 0


def test_a_partner_who_opted_out_is_refused(alex, blake, client_for):
    befriend(alex, blake)
    blake.allow_partner_logging = False
    blake.save(update_fields=["allow_partner_logging"])

    response = client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps(
            {"video_name": "Cossack Squat", "duration_s": 60, "partner_ids": [str(blake.pk)]}
        ),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert ExerciseEntry.objects.count() == 0


def test_the_partners_recent_list_says_who_logged_it(alex, blake, client_for):
    befriend(alex, blake)
    client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps(
            {"video_name": "Hip Airplane", "duration_s": 45, "partner_ids": [str(blake.pk)]}
        ),
        content_type="application/json",
    )

    theirs = client_for(blake).get("/api/v1/fitness/recent").json()[0]
    mine = client_for(alex).get("/api/v1/fitness/recent").json()[0]

    assert theirs["logged_by"] == "alex"
    # Solo-looking rows must not claim an author, or every entry reads as
    # somebody else's - log_exercise sets logged_by on the presser's row too.
    assert mine["logged_by"] is None


def test_the_picker_lists_only_friends_the_user_ticked(alex, blake, client_for):
    from apps.social import services as social

    befriend(alex, blake)

    assert client_for(alex).get("/api/v1/fitness/partners").json() == []

    social.set_prefs(alex, blake.pk, workout_partner=True)
    partners = client_for(alex).get("/api/v1/fitness/partners").json()

    assert [p["username"] for p in partners] == ["blake"]
    assert partners[0]["accepts_partner_logging"] is True
    # One-sided: alex ticking blake is not blake ticking alex.
    assert client_for(blake).get("/api/v1/fitness/partners").json() == []


def test_an_unticked_friend_can_still_be_completed_with(alex, blake, client_for):
    """The picker is a display filter, not a permission.

    If this starts failing, `workout_partner` has quietly become an access
    control that the Settings copy promises it is not.
    """
    befriend(alex, blake)

    response = client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps(
            {"video_name": "Jefferson Curl", "duration_s": 60, "partner_ids": [str(blake.pk)]}
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert ExerciseEntry.objects.filter(created_by=blake).count() == 1


def test_a_solo_completion_still_works_exactly_as_before(alex, client_for):
    response = client_for(alex).post(
        "/api/v1/fitness/complete",
        data=json.dumps({"video_name": "Wall Sit", "duration_s": 60}),
        content_type="application/json",
    )

    assert response.status_code == 200
    entry = ExerciseEntry.objects.get()
    assert entry.coop_group_id is None
    assert entry.created_by == alex
