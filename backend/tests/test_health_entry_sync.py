"""Phone sync for the hand-logged entry types — everything except gym.

The failures pinned here are the ones that look like success. A batch rejected
as a unit strands forty good entries behind one bad date; a batch accepted as a
unit drops the bad one from the phone forever with a 200 in the log. A replayed
request that creates second copies turns a dropped wifi connection into
duplicate data. None of them raise.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.health import services
from apps.health.entrysync import SPECS, SPECS_BY_KEY
from apps.health.models import (
    BmEntry,
    BodyMeasurement,
    BpEntry,
    DietEntry,
    Doc,
    ExerciseEntry,
    FitnessTest,
    Habit,
    HabitCompletion,
    LabResult,
    Note,
    OfficeDay,
    WeightEntry,
)

User = get_user_model()
PASSWORD = "x" * 14
ENDPOINT = "/api/v1/health/sync/entries"

NOW_MS = int(datetime(2026, 8, 10, 9, 30, tzinfo=UTC).timestamp() * 1000)


@pytest.fixture
def phone_user(db):
    return User.objects.create_user(username="phone", password=PASSWORD)


@pytest.fixture
def post(phone_user):
    client = Client()
    client.force_login(phone_user)

    def _post(payload: dict):
        return client.post(ENDPOINT, data=json.dumps(payload), content_type="application/json")

    return _post


def row(**extra) -> dict:
    return {"id": str(uuid.uuid4()), "updated_at": NOW_MS, "deleted": False, **extra}


#: One valid row of every type, so a change to a spec that breaks the mapping
#: fails here rather than on a phone.
def full_batch() -> dict:
    return {
        "diet": [row(timestamp=NOW_MS, name="Flat white")],
        "exercise": [row(timestamp=NOW_MS, video_name="Push-Up Challenge", duration_s=420)],
        "notes": [row(timestamp=NOW_MS, title="A note", content="hello")],
        "bm": [row(timestamp=NOW_MS, bristol=4, notes="fine")],
        "bp": [row(timestamp=NOW_MS, systolic=118, diastolic=76)],
        "weight": [row(timestamp=NOW_MS, weight_kg=81.4)],
        "body": [row(timestamp=NOW_MS, waist_cm=88.0, neck_cm=39.0)],
        "fitness": [row(timestamp=NOW_MS, grip_kg=48.5, dead_hang_s=41.0)],
        "docs": [row(timestamp=NOW_MS, title="Pathology result")],
        "labs": [row(date="2026-07-02", marker_name="Ferritin", value=95.0, unit="ug/L")],
        "office_days": [row(date="2026-08-06")],
        "habits": [row(name="Creatine", sort_order=1)],
        "habit_completions": [row(date="2026-08-10", habit_name="Creatine", completed_at=NOW_MS)],
    }


class TestEveryTypeLands:
    def test_one_row_of_each_type_is_stored(self, post, phone_user):
        payload = full_batch()
        response = post(payload)

        assert response.status_code == 200
        body = response.json()
        assert body["rejected"] == []
        assert len(body["accepted"]) == sum(len(v) for v in payload.values())
        assert body["created"] == len(body["accepted"])

    def test_the_batch_covers_every_declared_spec(self):
        """A new type added to SPECS must be exercised here, not just shipped."""
        assert set(full_batch()) == {spec.key for spec in SPECS}

    @pytest.mark.parametrize(
        ("model", "field", "expected"),
        [
            (DietEntry, "name", "Flat white"),
            (ExerciseEntry, "video_name", "Push-Up Challenge"),
            (ExerciseEntry, "duration_s", 420),
            (Note, "title", "A note"),
            (BmEntry, "bristol", 4),
            (BpEntry, "systolic", 118),
            (WeightEntry, "weight_kg", 81.4),
            (BodyMeasurement, "waist_cm", 88.0),
            (FitnessTest, "grip_kg", 48.5),
            (Doc, "title", "Pathology result"),
            (LabResult, "marker_name", "Ferritin"),
            (Habit, "name", "Creatine"),
            (HabitCompletion, "habit_name", "Creatine"),
        ],
    )
    def test_fields_map_to_the_right_columns(self, post, phone_user, model, field, expected):
        post(full_batch())
        stored = model.objects.get(created_by=phone_user)
        assert getattr(stored, field) == expected

    def test_the_phones_uuid_becomes_the_client_id(self, post, phone_user):
        payload = {"weight": [row(timestamp=NOW_MS, weight_kg=80.0)]}
        post(payload)
        stored = WeightEntry.objects.get(created_by=phone_user)
        assert str(stored.client_id) == payload["weight"][0]["id"]

    def test_bm_number_maps_onto_bristol(self, post, phone_user):
        """The phone calls it `bmNumber`; the portal calls it what it is."""
        post({"bm": [row(timestamp=NOW_MS, bristol=6)]})
        assert BmEntry.objects.get(created_by=phone_user).bristol == 6

    def test_office_day_is_the_date_it_names(self, post, phone_user):
        """The phone's file is called wfh and lists the opposite; see OfficeDay."""
        post({"office_days": [row(date="2026-08-06")]})
        assert str(OfficeDay.objects.get(created_by=phone_user).local_date) == "2026-08-06"


class TestPerRowOutcomes:
    """One bad row must not take the good ones with it, or be silently dropped."""

    def test_a_bad_row_is_rejected_by_name_and_the_rest_stored(self, post, phone_user):
        good = row(timestamp=NOW_MS, systolic=120, diastolic=80)
        bad = row(timestamp=NOW_MS, diastolic=80)  # no systolic

        body = post({"bp": [good, bad]}).json()

        assert body["accepted"] == [good["id"]]
        assert [r["id"] for r in body["rejected"]] == [bad["id"]]
        assert "systolic" in body["rejected"][0]["reason"]
        assert BpEntry.objects.filter(created_by=phone_user).count() == 1

    def test_an_out_of_range_bristol_is_a_rejection_not_a_500(self, post):
        body = post({"bm": [row(timestamp=NOW_MS, bristol=99)]}).json()
        assert body["accepted"] == []
        assert "1-7" in body["rejected"][0]["reason"]

    def test_an_unreadable_date_is_rejected_rather_than_guessed(self, post):
        """Filing an entry under the wrong day is invisible; a rejection is not."""
        body = post({"labs": [row(date="not a date", marker_name="B12", value=400)]}).json()
        assert "unreadable date" in body["rejected"][0]["reason"]

    def test_a_missing_timestamp_is_rejected(self, post):
        body = post({"weight": [row(weight_kg=80.0)]}).json()
        assert "unreadable timestamp" in body["rejected"][0]["reason"]

    def test_a_rejected_row_is_never_listed_as_accepted(self, post):
        """The phone marks synced exactly what `accepted` names."""
        body = post({"bm": [row(timestamp=NOW_MS, bristol=0)]}).json()
        rejected_ids = {r["id"] for r in body["rejected"]}
        assert rejected_ids.isdisjoint(set(body["accepted"]))

    def test_two_office_days_for_the_same_date_reject_the_second_not_the_batch(
        self, post, phone_user
    ):
        """OfficeDay is one row per day. A second phone row for a date already
        taken must be a named rejection, not a 500 that strands everything
        else in the same batch — including unrelated types sent alongside it.
        """
        first = row(date="2026-08-06")
        second = row(date="2026-08-06")
        weight = row(timestamp=NOW_MS, weight_kg=80.0)

        response = post({"office_days": [first, second], "weight": [weight]})
        body = response.json()

        assert response.status_code == 200
        # Order-independent: SPECS processes weight before office_days, and
        # that ordering is an implementation detail, not a contract.
        assert set(body["accepted"]) == {first["id"], weight["id"]}
        assert body["rejected"] == [
            {"id": second["id"], "reason": "conflicts with an existing record"}
        ]
        assert OfficeDay.objects.filter(created_by=phone_user).count() == 1
        assert WeightEntry.objects.filter(created_by=phone_user).count() == 1

    def test_an_unknown_type_is_ignored_not_fatal(self, post, phone_user):
        """A newer phone must degrade to "that type stays queued"."""
        response = post({"weight": [row(timestamp=NOW_MS, weight_kg=80.0)], "moonphase": []})
        assert response.status_code == 200
        assert WeightEntry.objects.filter(created_by=phone_user).count() == 1


class TestReplaySafety:
    def test_sending_the_same_batch_twice_creates_nothing_the_second_time(self, post, phone_user):
        """A reply lost to a dropped connection must be safe to resend."""
        payload = full_batch()
        first = post(payload).json()
        second = post(payload).json()

        assert second["created"] == 0
        assert second["unchanged"] == first["created"]
        assert set(second["accepted"]) == set(first["accepted"])
        assert WeightEntry.objects.filter(created_by=phone_user).count() == 1

    def test_a_newer_edit_wins(self, post, phone_user):
        original = row(timestamp=NOW_MS, weight_kg=80.0)
        post({"weight": [original]})

        edited = {**original, "weight_kg": 79.2, "updated_at": NOW_MS + 60_000}
        body = post({"weight": [edited]}).json()

        assert body["updated"] == 1
        assert WeightEntry.objects.get(created_by=phone_user).weight_kg == 79.2

    def test_a_stale_edit_does_not_overwrite(self, post, phone_user):
        """Two entries can arrive in the opposite order to the one they were edited in."""
        current = row(timestamp=NOW_MS, weight_kg=79.2, updated_at=NOW_MS + 60_000)
        post({"weight": [current]})

        stale = {**current, "weight_kg": 80.0, "updated_at": NOW_MS}
        body = post({"weight": [stale]}).json()

        assert body["unchanged"] == 1
        assert WeightEntry.objects.get(created_by=phone_user).weight_kg == 79.2


class TestDeletes:
    def test_a_delete_is_a_tombstone_not_a_removal(self, post, phone_user):
        """A hard delete would resurrect the row on the next sync."""
        entry = row(timestamp=NOW_MS, weight_kg=80.0)
        post({"weight": [entry]})

        body = post({"weight": [{**entry, "deleted": True, "updated_at": NOW_MS + 1}]}).json()

        assert body["deleted"] == 1
        stored = WeightEntry.objects.get(created_by=phone_user)
        assert stored.deleted_at is not None

    def test_a_deleted_row_stops_counting(self, post, phone_user):
        entry = row(timestamp=NOW_MS, weight_kg=80.0)
        post({"weight": [entry]})
        post({"weight": [{**entry, "deleted": True, "updated_at": NOW_MS + 1}]})

        assert services.entry_counts(phone_user)["weight"] == 0

    def test_a_row_created_and_deleted_before_it_ever_synced_is_accepted(self, post, phone_user):
        """Nothing to tombstone, but the phone must be told to stop resending."""
        body = post({"weight": [row(timestamp=NOW_MS, weight_kg=80.0, deleted=True)]}).json()

        assert len(body["accepted"]) == 1
        assert WeightEntry.objects.filter(created_by=phone_user).count() == 0


class TestOwnership:
    def test_a_client_id_belonging_to_someone_else_is_refused(self, post, db):
        """client_id is unique table-wide, so this would overwrite their entry."""
        other = User.objects.create_user(username="other", password=PASSWORD)
        theirs = row(timestamp=NOW_MS, weight_kg=70.0)
        other_client = Client()
        other_client.force_login(other)
        other_client.post(
            ENDPOINT, data=json.dumps({"weight": [theirs]}), content_type="application/json"
        )

        body = post({"weight": [{**theirs, "weight_kg": 99.0}]}).json()

        assert "another account" in body["rejected"][0]["reason"]
        assert WeightEntry.objects.get(client_id=theirs["id"]).weight_kg == 70.0

    def test_anonymous_callers_are_refused(self, db):
        response = Client().post(
            ENDPOINT, data=json.dumps({"weight": []}), content_type="application/json"
        )
        assert response.status_code == 401


class TestSideEffects:
    def test_habit_completions_link_to_the_habit_that_arrived_with_them(self, post, phone_user):
        """The completion can arrive before the definition that explains it."""
        post(full_batch())

        completion = HabitCompletion.objects.get(created_by=phone_user)
        assert completion.habit is not None
        assert completion.habit.name == "Creatine"

    def test_a_completion_without_its_habit_still_stores(self, post, phone_user):
        """habit_name is denormalised so a missing link is not lost data."""
        post({"habit_completions": [row(date="2026-08-10", habit_name="Unknown thing")]})

        completion = HabitCompletion.objects.get(created_by=phone_user)
        assert completion.habit is None
        assert completion.habit_name == "Unknown thing"

    def test_syncing_exercise_moves_the_daily_rollup(self, post, phone_user):
        """An entry that syncs but leaves the chart still reads as a failed sync."""
        from apps.health.models import DailyMetric

        post({"exercise": [row(timestamp=NOW_MS, video_name="Squats", duration_s=600)]})

        assert DailyMetric.objects.filter(
            user=phone_user, local_date="2026-08-10", metric="exercise_minutes"
        ).exists()

    def test_a_type_that_feeds_no_chart_does_not_claim_to(self):
        """Guards the rollup flags: only what rebuild() reads may set rollup."""
        rolled = {spec.key for spec in SPECS if spec.rollup}
        assert rolled == {"diet", "exercise", "bm", "bp", "weight", "habit_completions"}

    def test_an_empty_batch_is_a_no_op(self, post):
        body = post({}).json()
        assert body["accepted"] == []
        assert body["created"] == 0


def test_every_spec_key_is_a_field_on_the_wire_schema():
    """A spec with no matching schema field can never receive anything."""
    from apps.health.schemas import HealthEntrySyncIn

    assert set(SPECS_BY_KEY) <= set(HealthEntrySyncIn.model_fields)
