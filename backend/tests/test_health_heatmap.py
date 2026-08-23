"""The heatmap's thresholds and the grid built from them.

The failures worth pinning are the ones that still render a full, plausible
page: a curve that colours weight gain green, a band boundary off by one, a
column dropped for the wrong reason, a BMI computed against centimetres. None
of them raise, and all of them are wrong in the direction of being reassuring.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.health import scoring, services
from apps.health.models import DailyMetric, Profile

User = get_user_model()
PASSWORD = "x" * 14
TODAY = date.today()


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="heatmap", password=PASSWORD)


@pytest.fixture
def daily():
    def _daily(user, metric: str, value: float, *, offset: int = 0) -> DailyMetric:
        return DailyMetric.objects.create(
            user=user,
            local_date=TODAY - timedelta(days=offset),
            metric=metric,
            value=value,
            source=DailyMetric.Source.DEVICE,
        )

    return _daily


def column(grid: dict, key: str) -> dict:
    return next(c for c in grid["columns"] if c["key"] == key)


def cell(row: dict, key: str) -> dict:
    return next(c for c in row["cells"] if c["key"] == key)


class TestThresholdCurve:
    def test_clamped_outside_the_anchors(self):
        """Beyond the ends the score holds, rather than continuing the slope
        into a negative number or above one."""
        assert scoring.STEPS.score(0) == 0.0
        assert scoring.STEPS.score(-500) == 0.0
        assert scoring.STEPS.score(10_000) == 1.0
        assert scoring.STEPS.score(45_000) == 1.0

    def test_interpolates_between_anchors(self):
        # Halfway between (6000, 0.6) and (8000, 0.85).
        assert scoring.STEPS.score(7000) == pytest.approx(0.725)

    def test_sleep_is_scored_from_both_ends(self):
        """The one the min/max ramp could not express: 4 hours and 12 hours are
        both bad nights, and a one-sided scale has to call one of them good."""
        assert scoring.SLEEP_HOURS.score(8) == 1.0
        assert scoring.SLEEP_HOURS.score(4.5) < 0.3
        assert scoring.SLEEP_HOURS.score(11.5) < 0.6

    def test_resting_heart_rate_falls_as_it_rises(self):
        assert scoring.RESTING_HR.score(52) == 1.0
        assert scoring.RESTING_HR.score(64) < scoring.RESTING_HR.score(58)
        assert scoring.RESTING_HR.score(88) < 0.1

    def test_a_low_resting_heart_rate_is_not_penalised(self):
        """Fitness, not bradycardia. A grid that reds an athlete's 46 bpm has
        made a diagnosis it is not entitled to make."""
        assert scoring.RESTING_HR.score(40) == 1.0

    def test_weight_alone_is_never_coloured(self):
        """The bug this replaces: the old mapping ran red at 60 kg to green at
        80 kg, so gaining weight coloured green for everybody."""
        assert scoring.WEIGHT.scored is False
        assert scoring.WEIGHT.score(80) is None

    def test_bmi_peaks_in_the_normal_range(self):
        bmi = scoring.bmi_threshold()
        assert bmi.score(22) == 1.0
        assert bmi.score(17) < 0.3
        assert bmi.score(33) < 0.4


class TestBands:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [(0.0, 1), (0.19, 1), (0.2, 2), (0.4, 3), (0.6, 4), (0.79, 4), (0.8, 5), (1.0, 5)],
    )
    def test_boundaries(self, score, expected):
        """Five even steps, and 1.0 lands in the top band rather than a sixth."""
        assert scoring.band_for(score) == expected

    def test_no_score_is_no_band(self):
        assert scoring.band_for(None) is None


class TestVo2maxBanding:
    def test_age_shifts_the_curve_down(self):
        """Without this a fit 65-year-old reads red every day for being 65."""
        young = scoring.vo2max_threshold(age=25, sex="male")
        old = scoring.vo2max_threshold(age=65, sex="male")
        assert old.score(38) > young.score(38)

    def test_sex_shifts_the_curve(self):
        male = scoring.vo2max_threshold(age=40, sex="male")
        female = scoring.vo2max_threshold(age=40, sex="female")
        assert female.score(38) > male.score(38)

    def test_an_empty_profile_says_it_is_unadjusted(self):
        assert "Unadjusted" in scoring.vo2max_threshold().evidence


class TestGrid:
    def test_values_arrive_in_the_display_unit(self, owner, daily):
        """Sleep is stored in minutes and read in hours. Scoring the stored
        number against hour anchors would put every night in the bottom band."""
        daily(owner, "sleep_minutes", 465.0)
        row = services.heatmap(owner)["rows"][0]
        assert cell(row, "sleep_hours")["value"] == pytest.approx(7.75)
        assert cell(row, "sleep_hours")["band"] == 5

    def test_newest_day_first(self, owner, daily):
        for offset in range(3):
            daily(owner, "steps", 8000.0, offset=offset)
        dates = [row["date"] for row in services.heatmap(owner)["rows"]]
        assert dates == sorted(dates, reverse=True)

    def test_days_without_data_are_absent(self, owner, daily):
        daily(owner, "steps", 8000.0, offset=0)
        daily(owner, "steps", 8000.0, offset=5)
        assert len(services.heatmap(owner)["rows"]) == 2

    def test_columns_without_data_are_dropped(self, owner, daily):
        daily(owner, "steps", 8000.0)
        keys = [c["key"] for c in services.heatmap(owner)["columns"]]
        assert keys == ["steps"]

    def test_cells_align_with_columns(self, owner, daily):
        daily(owner, "steps", 8000.0)
        daily(owner, "resting_hr", 58.0)
        grid = services.heatmap(owner)
        keys = [c["key"] for c in grid["columns"]]
        for row in grid["rows"]:
            assert [c["key"] for c in row["cells"]] == keys

    def test_a_missing_metric_leaves_an_empty_cell(self, owner, daily):
        daily(owner, "steps", 8000.0, offset=0)
        daily(owner, "steps", 8000.0, offset=1)
        daily(owner, "resting_hr", 58.0, offset=0)
        older = services.heatmap(owner)["rows"][1]
        assert cell(older, "resting_hr") == {
            "key": "resting_hr",
            "value": None,
            "score": None,
            "band": None,
        }

    def test_the_window_is_inclusive_of_today(self, owner, daily):
        daily(owner, "steps", 8000.0, offset=0)
        daily(owner, "steps", 8000.0, offset=29)
        daily(owner, "steps", 8000.0, offset=30)
        assert len(services.heatmap(owner, days=30)["rows"]) == 2

    def test_another_users_days_never_appear(self, owner, daily, db):
        other = User.objects.create_user(username="other", password=PASSWORD)
        daily(other, "steps", 8000.0)
        assert services.heatmap(owner)["rows"] == []


class TestDayScore:
    def test_is_the_mean_of_the_scored_cells(self, owner, daily):
        daily(owner, "steps", 10_000.0)  # 1.0
        daily(owner, "resting_hr", 70.0)  # 0.5
        row = services.heatmap(owner)["rows"][0]
        assert row["score"] == pytest.approx(0.75)
        assert row["scored_count"] == 2

    def test_ignores_the_uncoloured_columns(self, owner, daily):
        """Weight has no threshold. Counting it as a zero would drag every day
        that recorded one into the red for having been weighed."""
        daily(owner, "steps", 10_000.0)
        daily(owner, "weight_kg", 76.0)
        row = services.heatmap(owner)["rows"][0]
        assert row["scored_count"] == 1
        assert row["score"] == 1.0

    def test_a_day_with_nothing_scorable_has_no_score(self, owner, daily):
        daily(owner, "weight_kg", 76.0)
        row = services.heatmap(owner)["rows"][0]
        assert row["score"] is None
        assert row["band"] is None


class TestProfileDerivedColumns:
    def test_bmi_appears_only_with_a_height(self, owner, daily):
        daily(owner, "weight_kg", 76.0)
        assert "bmi" not in {c["key"] for c in services.heatmap(owner)["columns"]}

        Profile.objects.create(user=owner, height_cm=178.0)
        grid = services.heatmap(owner)
        assert cell(grid["rows"][0], "bmi")["value"] == pytest.approx(76 / 1.78**2)

    def test_active_minutes_sums_the_two_buckets(self, owner, daily):
        daily(owner, "fairly_active_minutes", 12.0)
        daily(owner, "very_active_minutes", 25.0)
        assert cell(services.heatmap(owner)["rows"][0], "active_minutes")["value"] == 37.0

    def test_active_minutes_is_absent_rather_than_zero(self, owner, daily):
        """The trap the column exists to avoid. `active_zone_minutes` is stored
        as a literal 0.0 on every day the device never sent it, so scoring that
        metric drew a solid red stripe for someone averaging 37 vigorous
        minutes a day. A day with neither bucket has no cell at all."""
        daily(owner, "active_zone_minutes", 0.0)
        daily(owner, "steps", 14_000.0)
        grid = services.heatmap(owner)
        assert "active_zone_minutes" not in {c["key"] for c in grid["columns"]}
        assert "active_minutes" not in {c["key"] for c in grid["columns"]}

    def test_one_bucket_alone_still_counts(self, owner, daily):
        daily(owner, "very_active_minutes", 25.0)
        assert cell(services.heatmap(owner)["rows"][0], "active_minutes")["value"] == 25.0

    def test_bmi_uses_metres_not_centimetres(self, owner, daily):
        """The slip that produces a BMI of 0.0024 and a uniformly red column."""
        Profile.objects.create(user=owner, height_cm=178.0)
        daily(owner, "weight_kg", 76.0)
        value = cell(services.heatmap(owner)["rows"][0], "bmi")["value"]
        assert 15 < value < 40


class TestColumnSummary:
    def test_mean_score_covers_only_the_days_with_values(self, owner, daily):
        daily(owner, "steps", 10_000.0, offset=0)  # 1.0
        daily(owner, "steps", 4_000.0, offset=1)  # 0.35
        daily(owner, "resting_hr", 58.0, offset=0)
        steps = column(services.heatmap(owner), "steps")
        assert steps["days"] == 2
        assert steps["mean_score"] == pytest.approx(0.675)

    def test_every_column_carries_its_evidence(self, owner, daily):
        """A colour that cannot say why it is red is decoration."""
        for metric in ("steps", "sleep_minutes", "weight_kg", "resting_hr"):
            daily(owner, metric, 100.0)
        for entry in services.heatmap(owner)["columns"]:
            assert entry["evidence"]
