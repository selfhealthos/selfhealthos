"""The Body page: its thresholds, its table, and the two ways to write to it.

The failures pinned here are the ones that still render a complete, plausible
page. A waist-to-height ratio divided in mismatched units reads 0.9 for a
perfectly healthy person and paints the column red. A PATCH of the target
weight that quietly drops the height takes every BMI in the table with it and
leaves no error anywhere. A table that carries a stale weight forward colours
nine days on the strength of one weigh-in. None of these raise.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.core.exceptions import DomainError
from apps.health import scoring, services
from apps.health.models import BodyMeasurement, Profile, WeightEntry

User = get_user_model()
PASSWORD = "x" * 14
TODAY = date.today()


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="body", password=PASSWORD, sex="male")


@pytest.fixture
def measured(owner):
    """A profile with a height, so the derived columns exist at all."""
    Profile.objects.update_or_create(user=owner, defaults={"height_cm": 178.0})
    return owner


def column(grid: dict, key: str) -> dict | None:
    return next((c for c in grid["columns"] if c["key"] == key), None)


def cell(row: dict, key: str) -> dict:
    return next(c for c in row["cells"] if c["key"] == key)


def row_on(grid: dict, day: date) -> dict:
    return next(r for r in grid["rows"] if r["date"] == day)


class TestWaistHeightThreshold:
    def test_peaks_across_the_healthy_range(self):
        """0.4-0.49 is the healthy band, so it scores full marks across it -
        not at one point in the middle with a slope either side."""
        wthr = scoring.waist_height_threshold()
        assert wthr.score(0.43) == 1.0
        assert wthr.score(0.45) == 1.0
        assert wthr.score(0.47) == 1.0

    def test_falls_away_above_the_half_height_limit(self):
        wthr = scoring.waist_height_threshold()
        assert wthr.score(0.50) < wthr.score(0.47)
        assert wthr.score(0.60) < wthr.score(0.50)
        assert wthr.score(0.75) == 0.0

    def test_scored_from_both_ends(self):
        """The two-sided optimum. A ratio of 0.32 is underweight or a tape
        measure read wrong, not a better result than 0.45 - a one-sided ramp
        would have to call it the best day on record."""
        wthr = scoring.waist_height_threshold()
        assert wthr.score(0.30) < 0.5
        assert wthr.score(0.30) < wthr.score(0.45)


class TestWaistThreshold:
    def test_unscored_without_a_sex(self):
        """The male and female cut-offs are 14 cm apart. Guessing one puts a
        confident colour on an 82 cm waist that a coin toss decided."""
        assert scoring.waist_threshold(sex="").scored is False
        assert scoring.waist_threshold(sex="").score(82) is None

    def test_bands_on_the_who_cutoffs_per_sex(self):
        male = scoring.waist_threshold(sex="male")
        female = scoring.waist_threshold(sex="female")
        # 82 cm is comfortably healthy for a man and past the female cut-off.
        assert male.score(82) == 1.0
        assert female.score(82) < 1.0
        assert female.score(70) == 1.0

    def test_does_not_reward_an_implausibly_small_waist(self):
        male = scoring.waist_threshold(sex="male")
        assert male.score(60) < male.score(78)


class TestWeightThreshold:
    def test_unscored_without_a_target(self):
        """`scoring.WEIGHT`'s reasoning, unchanged: there is no population
        threshold for a weight, and the dashboard this replaced coloured 80 kg
        green and 60 kg red for everyone."""
        assert scoring.weight_threshold(target_kg=None).scored is False
        assert scoring.weight_threshold(target_kg=0).scored is False

    def test_peaks_at_the_users_own_target(self):
        weight = scoring.weight_threshold(target_kg=80)
        assert weight.score(80) == 1.0
        assert weight.score(80) > weight.score(85)

    def test_symmetric_because_nothing_here_knows_the_goal(self):
        """Nothing records whether the target is to lose or to gain, so 3 kg
        under scores exactly what 3 kg over does."""
        weight = scoring.weight_threshold(target_kg=80)
        assert weight.score(77) == pytest.approx(weight.score(83))

    def test_names_the_target_in_its_evidence(self):
        """The colour has to be explicable on the page: it means "against the
        number you chose", and the only way a reader knows that is if the
        column says so."""
        assert "80" in scoring.weight_threshold(target_kg=80).evidence


class TestBodyColumns:
    def test_derived_columns_dropped_without_a_height(self, owner):
        columns = scoring.body_columns_for(sex="male", height_cm=None)
        keys = [c.key for c in columns.columns]
        assert "bmi" not in keys
        assert "waist_height_ratio" not in keys
        assert keys == ["weight_kg", "waist_cm"]

    def test_full_set_with_a_height(self, owner):
        columns = scoring.body_columns_for(sex="male", height_cm=178)
        assert [c.key for c in columns.columns] == [
            "weight_kg",
            "bmi",
            "waist_cm",
            "waist_height_ratio",
        ]


class TestBodyTable:
    def test_ratio_uses_matching_units(self, measured):
        """The one that renders a full red page and raises nothing: waist is
        stored in centimetres and height in metres, so dividing them as stored
        gives 0.9 for a 90 cm waist on a 178 cm person - the "high risk" band
        for a ratio that is actually 0.51."""
        services.log_measurement(measured, waist_cm=90.0)
        grid = services.body_history(measured)
        value = cell(row_on(grid, TODAY), "waist_height_ratio")["value"]
        assert value == pytest.approx(0.5056, abs=1e-3)

    def test_bmi_uses_metres_not_centimetres(self, measured):
        services.log_entry(measured, kind="weight", value=80.0)
        grid = services.body_history(measured)
        assert cell(row_on(grid, TODAY), "bmi")["value"] == pytest.approx(25.25, abs=0.01)

    def test_rows_only_for_days_with_a_reading(self, measured):
        """Not one row per calendar day. A 730-day window with eleven weigh-ins
        is a table of eleven rows, not 719 rows of em-dashes."""
        services.log_entry(measured, kind="weight", value=80.0)
        services.log_entry(measured, kind="weight", value=79.5, on=TODAY - timedelta(days=10))
        grid = services.body_history(measured)
        assert [r["date"] for r in grid["rows"]] == [TODAY, TODAY - timedelta(days=10)]

    def test_weight_is_not_carried_forward(self, measured):
        """A weight repeated down the column would colour days nobody stood on
        the scales, and the colour is the part a reader trusts."""
        services.log_entry(measured, kind="weight", value=80.0, on=TODAY - timedelta(days=5))
        services.log_measurement(measured, waist_cm=90.0)
        grid = services.body_history(measured)
        today_row = row_on(grid, TODAY)
        assert cell(today_row, "weight_kg")["value"] is None
        assert cell(today_row, "bmi")["value"] is None
        assert cell(today_row, "waist_cm")["value"] == 90.0

    def test_newest_first(self, measured):
        services.log_entry(measured, kind="weight", value=80.0, on=TODAY - timedelta(days=3))
        services.log_entry(measured, kind="weight", value=81.0)
        grid = services.body_history(measured)
        assert grid["rows"][0]["date"] == TODAY

    def test_weight_column_uncoloured_without_a_target(self, measured):
        services.log_entry(measured, kind="weight", value=80.0)
        grid = services.body_history(measured)
        assert column(grid, "weight_kg")["scored"] is False
        assert cell(row_on(grid, TODAY), "weight_kg")["band"] is None
        # The BMI beside it still bands - a height is enough for that.
        assert cell(row_on(grid, TODAY), "bmi")["band"] is not None

    def test_weight_column_bands_once_a_target_is_set(self, measured):
        services.set_body_profile(measured, target_weight_kg=80.0, fields={"target_weight_kg"})
        services.log_entry(measured, kind="weight", value=80.0)
        grid = services.body_history(measured)
        assert column(grid, "weight_kg")["scored"] is True
        assert cell(row_on(grid, TODAY), "weight_kg")["band"] == 5

    def test_last_weigh_in_of_the_day_wins(self, measured):
        """Matching the rollup: a morning and an evening weigh-in are two
        readings of a number that moved, not two samples of one number."""
        services.log_entry(measured, kind="weight", value=80.0)
        services.log_entry(measured, kind="weight", value=79.0)
        grid = services.body_history(measured)
        assert cell(row_on(grid, TODAY), "weight_kg")["value"] == 79.0

    def test_latest_measurement_of_the_day_wins(self, measured):
        services.log_measurement(measured, waist_cm=90.0)
        services.log_measurement(measured, waist_cm=88.0)
        grid = services.body_history(measured)
        assert cell(row_on(grid, TODAY), "waist_cm")["value"] == 88.0


class TestLogMeasurement:
    def test_rejects_a_row_of_nothing(self, owner):
        """Four nulls is a date, not a measurement. Stored, it becomes a table
        row of em-dashes that reads as data loss."""
        with pytest.raises(DomainError):
            services.log_measurement(owner)

    def test_rejects_zero(self, owner):
        """Zero is not a measurement of anything, and stored it would score as
        the worst waist ever recorded."""
        with pytest.raises(DomainError):
            services.log_measurement(owner, waist_cm=0)

    def test_carries_no_client_id(self, owner):
        """`client_id` is the phone's global identity key - devicesync rejects
        one presented by a different owner, so minting one here would break the
        device's own sync."""
        entry, _ = services.log_measurement(owner, waist_cm=90.0)
        assert entry.client_id in (None, "")

    def test_local_date_comes_from_the_users_timezone(self, owner):
        entry, _ = services.log_measurement(owner, waist_cm=90.0)
        assert entry.local_date == TODAY

    def test_backdated_entry_files_under_the_day_given(self, owner):
        when = TODAY - timedelta(days=30)
        entry, _ = services.log_measurement(owner, waist_cm=90.0, on=when)
        assert entry.local_date == when
        # A real instant on that day, not the moment it was typed.
        assert entry.occurred_at.date() in (
            when,
            when - timedelta(days=1),
            when + timedelta(days=1),
        )


class TestBodyProfile:
    def test_patching_the_target_keeps_the_height(self, measured):
        """The one that silently empties the BMI column: two separate forms
        write this row, and a PUT-shaped update from the target-weight form
        wipes the height the other form set."""
        services.set_body_profile(measured, target_weight_kg=80.0, fields={"target_weight_kg"})
        assert services.body_profile(measured)["height_cm"] == 178.0

    def test_patching_the_height_keeps_the_target(self, measured):
        services.set_body_profile(measured, target_weight_kg=80.0, fields={"target_weight_kg"})
        services.set_body_profile(measured, height_cm=180.0, fields={"height_cm"})
        stored = services.body_profile(measured)
        assert stored == {"height_cm": 180.0, "target_weight_kg": 80.0}

    def test_explicit_null_clears_the_field(self, measured):
        services.set_body_profile(measured, height_cm=None, fields={"height_cm"})
        assert services.body_profile(measured)["height_cm"] is None

    def test_rejects_a_height_in_metres(self, owner):
        """The unit slip that produces a BMI of 26,800 and a table of red cells
        nobody can explain. An inches slip is not catchable this way and is not
        claimed to be: 70 is a real height in centimetres."""
        with pytest.raises(DomainError):
            services.set_body_profile(owner, height_cm=1.78, fields={"height_cm"})

    def test_reads_without_creating_a_profile_row(self, owner):
        assert services.body_profile(owner) == {"height_cm": None, "target_weight_kg": None}
        assert not Profile.objects.filter(user=owner).exists()


class TestBodyApi:
    def test_weight_post_creates_and_rolls_up(self, measured, client_for):
        """The rollup runs inline. A weight that does not move the chart until
        the nightly job reads exactly like the write having failed."""
        client = client_for(measured)
        res = client.post(
            "/api/v1/health/body/weight",
            data={"weight_kg": 80.5},
            content_type="application/json",
        )
        assert res.status_code == 201
        assert WeightEntry.objects.filter(created_by=measured).count() == 1

        grid = client.get("/api/v1/health/body").json()
        today = next(r for r in grid["rows"] if r["date"] == TODAY.isoformat())
        assert next(c for c in today["cells"] if c["key"] == "weight_kg")["value"] == 80.5

    def test_measurement_post_creates(self, measured, client_for):
        res = client_for(measured).post(
            "/api/v1/health/body/measurement",
            data={"waist_cm": 90.0},
            content_type="application/json",
        )
        assert res.status_code == 201
        assert BodyMeasurement.objects.filter(created_by=measured).count() == 1

    def test_measurement_post_rejects_an_empty_row(self, measured, client_for):
        res = client_for(measured).post(
            "/api/v1/health/body/measurement",
            data={"notes": "forgot the tape"},
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_profile_patch_is_partial(self, measured, client_for):
        client = client_for(measured)
        res = client.patch(
            "/api/v1/health/body/profile",
            data={"target_weight_kg": 78.0},
            content_type="application/json",
        )
        assert res.status_code == 200
        assert res.json() == {"height_cm": 178.0, "target_weight_kg": 78.0}

    def test_profile_patch_rejects_an_implausible_height(self, measured, client_for):
        res = client_for(measured).patch(
            "/api/v1/health/body/profile",
            data={"height_cm": 1.78},
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_body_no_longer_carries_the_fitness_tests(self, measured, client_for):
        """They moved to /health/fitness. Bundled, every Body request paid for
        a query the page stopped drawing."""
        body = client_for(measured).get("/api/v1/health/body").json()
        assert "tests" not in body

    def test_fitness_endpoint_serves_the_tests(self, measured, client_for):
        res = client_for(measured).get("/api/v1/health/fitness")
        assert res.status_code == 200
        assert res.json()["tests"] == []

    def test_another_user_sees_none_of_it(self, measured, client_for, db):
        """Ownership, unchanged: the friend graph grants a write, never a read."""
        services.log_entry(measured, kind="weight", value=80.0)
        stranger = User.objects.create_user(username="stranger", password=PASSWORD)
        grid = client_for(stranger).get("/api/v1/health/body").json()
        assert grid["rows"] == []
