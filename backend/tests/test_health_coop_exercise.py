"""Working out with a friend: one press of Complete, one row per participant.

Every test here pins something a plausible reimplementation gets wrong - the
partner's row landing on the wrong dashboard, both rows sharing a client_id,
the timezone coming from the wrong person, or the intended two-people-in-a-room
case silently doubling everyone's minutes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model

from apps.health import services
from apps.health.models import DailyMetric, ExerciseEntry
from apps.social import services as social

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    return User.objects.create_user(
        username="alex", password=PASSWORD, timezone="Australia/Melbourne"
    )


@pytest.fixture
def blake(db):
    return User.objects.create_user(
        username="blake", password=PASSWORD, timezone="Australia/Melbourne"
    )


def befriend(a, b):
    social.send_request(a, username=b.username)
    social.accept_request(b, social.get_friendship(a, b).pk)


def test_one_press_writes_a_row_for_each_participant(alex, blake):
    befriend(alex, blake)

    entries = services.log_shared_exercise(
        alex, video_name="Deep Squat Hold", duration_s=90, partners=[blake]
    )

    assert len(entries) == 2
    assert {e.created_by for e in entries} == {alex, blake}
    # One press, one group.
    assert len({e.coop_group_id for e in entries}) == 1
    assert entries[0].coop_group_id is not None


def test_the_partners_row_belongs_to_the_partner_not_the_presser(alex, blake):
    befriend(alex, blake)

    services.log_shared_exercise(alex, video_name="Cossack Squat", duration_s=60, partners=[blake])

    theirs = ExerciseEntry.objects.get(created_by=blake)
    # created_by is what every read filters on; logged_by is only attribution.
    assert theirs.created_by == blake
    assert theirs.logged_by == alex
    assert ExerciseEntry.objects.filter(created_by=alex).count() == 1


def test_no_row_in_the_group_reuses_a_client_id(alex, blake):
    """client_id is globally unique and devicesync rejects a foreign owner.

    A fan-out that shared one id would break phone sync for everyone in the
    group, so partner rows carry none at all.
    """
    befriend(alex, blake)

    services.log_shared_exercise(alex, video_name="Hip Airplane", duration_s=45, partners=[blake])

    assert list(ExerciseEntry.objects.values_list("client_id", flat=True)) == [None, None]


def test_each_participants_local_date_comes_from_their_own_timezone(alex, blake):
    befriend(alex, blake)
    blake.timezone = "Europe/London"
    blake.save(update_fields=["timezone"])
    # 22:30 UTC: already the 2nd in Melbourne, still the 1st in London.
    at = datetime(2026, 3, 1, 22, 30, tzinfo=UTC)

    services.log_shared_exercise(
        alex, video_name="Jefferson Curl", duration_s=60, partners=[blake], at=at
    )

    assert str(ExerciseEntry.objects.get(created_by=alex).local_date) == "2026-03-02"
    assert str(ExerciseEntry.objects.get(created_by=blake).local_date) == "2026-03-01"


def test_both_participants_charts_move(alex, blake):
    befriend(alex, blake)

    services.log_shared_exercise(alex, video_name="90/90 Switch", duration_s=600, partners=[blake])

    for who in (alex, blake):
        minutes = DailyMetric.objects.filter(user=who, metric="exercise_minutes").first()
        assert minutes is not None, f"{who.username}'s rollup was never rebuilt"
        assert minutes.value == pytest.approx(10.0)


def test_both_people_pressing_complete_does_not_double_anyone(alex, blake):
    """The intended use case: two phones, one room, both tick the other.

    Without the dedupe this is four rows and doubled minutes for both - and it
    happens every session, not in some edge case.
    """
    befriend(alex, blake)

    services.log_shared_exercise(
        alex, video_name="Deep Squat Hold", duration_s=90, partners=[blake]
    )
    services.log_shared_exercise(
        blake, video_name="Deep Squat Hold", duration_s=90, partners=[alex]
    )

    assert ExerciseEntry.objects.filter(created_by=alex).count() == 1
    assert ExerciseEntry.objects.filter(created_by=blake).count() == 1


def test_the_same_exercise_later_in_the_session_is_a_real_second_entry(alex, blake):
    befriend(alex, blake)
    first = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    much_later = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)

    services.log_shared_exercise(
        alex, video_name="Deep Squat Hold", duration_s=90, partners=[blake], at=first
    )
    services.log_shared_exercise(
        alex, video_name="Deep Squat Hold", duration_s=90, partners=[blake], at=much_later
    )

    assert ExerciseEntry.objects.filter(created_by=blake).count() == 2


def test_a_solo_session_is_unchanged_by_any_of_this(alex):
    entry = services.log_exercise(alex, video_name="Wall Sit", duration_s=60)

    assert entry.coop_group_id is None
    assert entry.logged_by == alex
    assert entry.created_by == alex


def test_a_solo_repeat_is_never_deduped(alex):
    """Dedupe belongs to shared sessions only.

    Silently dropping a solo re-log would be a behaviour change to a path that
    has nothing to do with this feature.
    """
    services.log_exercise(alex, video_name="Wall Sit", duration_s=60)
    services.log_exercise(alex, video_name="Wall Sit", duration_s=60)

    assert ExerciseEntry.objects.filter(created_by=alex).count() == 2


def test_log_shared_exercise_with_no_partners_takes_the_solo_path(alex):
    entries = services.log_shared_exercise(alex, video_name="Wall Sit", duration_s=60)

    assert len(entries) == 1
    assert entries[0].coop_group_id is None
