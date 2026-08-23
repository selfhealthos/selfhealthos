"""Sleep architecture and overnight oximetry.

The failures worth pinning are the ones that produce a plausible night: a WASO
that counts the time spent reading before sleep, a cycle count that doubles
because of one stir mid-REM, a desaturation baseline dragged down by the dip it
is supposed to be measuring. All of them render as a normal-looking page.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.health import nights
from apps.health.models import Sample, SleepSegment, SleepSession

User = get_user_model()
PASSWORD = "x" * 14
NIGHT = date(2026, 8, 12)
#: 22:00 the evening before, in UTC. Every offset below is minutes from here.
LIGHTS_OUT = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="nights", password=PASSWORD)


@pytest.fixture
def session(owner):
    return SleepSession.objects.create(
        user=owner,
        external_id="log-1",
        local_date=NIGHT,
        started_at=LIGHTS_OUT,
        ended_at=LIGHTS_OUT + timedelta(hours=8),
        duration_minutes=450,
        efficiency=92,
    )


def stage(session, level: str, *, at: int, minutes: int, short: bool = False) -> SleepSegment:
    """A `minutes`-long run of `level`, starting `at` minutes after lights out."""
    started = LIGHTS_OUT + timedelta(minutes=at)
    return SleepSegment.objects.create(
        session=session,
        started_at=started,
        ended_at=started + timedelta(minutes=minutes),
        seconds=minutes * 60,
        level=level,
        is_short=short,
    )


def spans(session) -> list[nights.Span]:
    return [
        nights.Span(
            level=row.level,
            started_at=row.started_at,
            ended_at=row.ended_at,
            seconds=row.seconds,
            is_short=row.is_short,
        )
        for row in SleepSegment.objects.filter(session=session, is_short=False).order_by(
            "started_at"
        )
    ]


def minutes(values: list[float], *, at: int = 0) -> list[dict]:
    """One reading per minute, starting `at` minutes after lights out."""
    return [
        {"at": LIGHTS_OUT + timedelta(minutes=at + index), "value": value}
        for index, value in enumerate(values)
    ]


class TestArchitecture:
    def test_sleep_onset_is_time_to_the_first_sleep(self, session):
        stage(session, "wake", at=0, minutes=18)
        stage(session, "light", at=18, minutes=60)
        assert nights.architecture(spans(session))["sleep_onset_minutes"] == 18

    def test_waso_excludes_the_time_before_falling_asleep(self, session):
        """The failure that makes a normal night look broken: 18 minutes spent
        reading is latency, and counting it as fragmented sleep says the night
        was interrupted when it had not started."""
        stage(session, "wake", at=0, minutes=18)
        stage(session, "light", at=18, minutes=60)
        stage(session, "wake", at=78, minutes=12)
        stage(session, "light", at=90, minutes=60)
        result = nights.architecture(spans(session))
        assert result["waso_minutes"] == 12
        assert result["wake_episodes"] == 1

    def test_waso_excludes_lying_awake_after_the_last_sleep(self, session):
        stage(session, "light", at=0, minutes=60)
        stage(session, "wake", at=60, minutes=25)
        assert nights.architecture(spans(session))["waso_minutes"] == 0

    def test_longest_wake_separates_one_bad_wake_from_many_stirs(self, session):
        """`minutes_awake` counts the same 40 minutes either way, which is why
        the totals cannot answer the question this does."""
        stage(session, "light", at=0, minutes=30)
        for offset in range(30, 90, 10):
            stage(session, "wake", at=offset, minutes=5)
            stage(session, "light", at=offset + 5, minutes=5)
        stage(session, "light", at=90, minutes=30)
        result = nights.architecture(spans(session))
        assert result["wake_episodes"] == 6
        assert result["longest_wake_minutes"] == 5

    def test_rem_latency_runs_from_falling_asleep(self, session):
        stage(session, "wake", at=0, minutes=10)
        stage(session, "light", at=10, minutes=50)
        stage(session, "deep", at=60, minutes=30)
        stage(session, "rem", at=90, minutes=20)
        assert nights.architecture(spans(session))["rem_latency_minutes"] == 80

    def test_stage_share_is_of_sleep_not_of_time_in_bed(self, session):
        """Dividing by time in bed reports a lower deep-sleep percentage on a
        restless night purely because of the wake time in the denominator."""
        stage(session, "deep", at=0, minutes=60)
        stage(session, "light", at=60, minutes=120)
        stage(session, "rem", at=180, minutes=60)
        stage(session, "wake", at=240, minutes=60)
        share = nights.architecture(spans(session))["stage_share"]
        assert share["deep"] == pytest.approx(25.0)
        assert share["rem"] == pytest.approx(25.0)
        assert share["light"] == pytest.approx(50.0)


class TestCycles:
    def test_one_cycle_per_rem_period(self, session):
        for index in range(4):
            start = index * 90
            stage(session, "light", at=start, minutes=40)
            stage(session, "deep", at=start + 40, minutes=30)
            stage(session, "rem", at=start + 70, minutes=20)
        assert nights.architecture(spans(session))["cycles"] == 4

    def test_a_stir_mid_rem_does_not_split_the_cycle(self, session):
        """Two REM runs three minutes apart are one REM period interrupted.
        Counting them separately doubles the cycle count and reports fragmented
        architecture on an ordinary night."""
        stage(session, "light", at=0, minutes=60)
        stage(session, "rem", at=60, minutes=15)
        stage(session, "wake", at=75, minutes=3)
        stage(session, "rem", at=78, minutes=12)
        result = nights.architecture(spans(session))
        assert result["cycles"] == 1
        assert result["rem_periods"][0]["minutes"] == 30

    def test_rem_periods_far_apart_stay_separate(self, session):
        stage(session, "rem", at=60, minutes=15)
        stage(session, "light", at=75, minutes=40)
        stage(session, "rem", at=115, minutes=20)
        assert nights.architecture(spans(session))["cycles"] == 2

    def test_a_night_with_no_segments_is_empty_not_wrong(self, session):
        result = nights.architecture([])
        assert result["cycles"] == 0
        assert result["sleep_onset_minutes"] is None


class TestOxygen:
    def test_reports_the_nadir_the_average_hides(self):
        """The whole argument for the change: this night averages 95.7% and
        spends four minutes at 84%."""
        values = [96.0] * 60 + [84.0] * 4 + [96.0] * 60
        result = nights.oxygen(minutes(values))
        assert result["minimum"] == 84.0
        assert result["mean"] > 95
        assert result["minutes_under_90"] == 4
        assert result["minutes_under_88"] == 4

    def test_lowest_at_carries_the_time(self):
        values = [96.0] * 30 + [88.0] + [96.0] * 30
        result = nights.oxygen(minutes(values))
        assert result["lowest_at"] == LIGHTS_OUT + timedelta(minutes=30)

    def test_a_dip_is_measured_against_the_preceding_minutes(self):
        values = [96.0] * 30 + [91.0] * 3 + [96.0] * 30
        dips = nights.oxygen(minutes(values))["dips"]
        assert len(dips) == 1
        assert dips[0]["lowest"] == 91.0
        assert dips[0]["drop"] == 5.0

    def test_the_dip_does_not_drag_down_its_own_baseline(self):
        """A mean baseline over a window containing the dip lowers the bar the
        dip is measured against, and a long desaturation stops registering
        partway through. The median is what stops that."""
        values = [96.0] * 30 + [90.0] * 8 + [96.0] * 20
        dips = nights.oxygen(minutes(values))["dips"]
        assert len(dips) == 1
        assert dips[0]["minutes"] == 9

    def test_a_slow_drift_is_not_a_desaturation(self):
        """Falling one point every ten minutes is not a dip, and a whole-night
        baseline would score the back half of the night as one."""
        values = [96.0 - index // 10 for index in range(120)]
        assert nights.oxygen(minutes(values))["dips"] == []

    def test_events_per_hour_is_reported_at_both_thresholds(self):
        values = ([96.0] * 20 + [91.0] * 2) * 5
        result = nights.oxygen(minutes(values))
        assert set(result["events_per_hour"]) == {"3pct", "4pct"}
        assert result["events_per_hour"]["3pct"] >= result["events_per_hour"]["4pct"]

    def test_no_readings_is_zero_not_a_crash(self):
        result = nights.oxygen([])
        assert result["minimum"] is None
        assert result["dips"] == []
        assert result["events_per_hour"] == {}


class TestDetail:
    def test_clips_the_series_to_the_session(self, owner, session):
        """A full day of heart rate on the night's axis squeezes the eight
        hours that matter into a third of the width."""
        for offset in range(-120, 600, 30):
            Sample.objects.create(
                user=owner,
                metric="hr",
                ts=LIGHTS_OUT + timedelta(minutes=offset),
                value=58.0,
            )
        found = nights.detail(owner, NIGHT)
        stamps = [point["at"] for point in found["series"]["hr"]]
        assert min(stamps) >= session.started_at
        assert max(stamps) <= session.ended_at

    def test_short_wakes_are_kept_out_of_the_architecture(self, owner, session):
        """`shortData` overlays the trace rather than interrupting it; folding
        the stirs in would shatter every stage block they land in."""
        stage(session, "light", at=0, minutes=120)
        stage(session, "wake", at=45, minutes=1, short=True)
        found = nights.detail(owner, NIGHT)
        assert found["architecture"]["wake_episodes"] == 0
        assert any(segment["is_short"] for segment in found["segments"])

    def test_a_night_without_segments_says_so(self, owner, session):
        found = nights.detail(owner, NIGHT)
        assert found["has_hypnogram"] is False
        assert found["session"]["duration_minutes"] == 450

    def test_no_session_is_none(self, owner):
        assert nights.detail(owner, date(2020, 1, 1)) is None

    def test_another_users_night_is_not_visible(self, owner, session, db):
        other = User.objects.create_user(username="other-night", password=PASSWORD)
        assert nights.detail(other, NIGHT) is None


# --------------------------------------------------------------------------
# The night against its history, and the window summary
# --------------------------------------------------------------------------


def a_night(user, on: date, *, minutes: int, efficiency: int = 92, hour: int = 12) -> SleepSession:
    """One session on `on`. `hour` is UTC, so 12 is a 22:00 Melbourne bedtime."""
    started = datetime(on.year, on.month, on.day, hour, 0, tzinfo=UTC) - timedelta(days=1)
    return SleepSession.objects.create(
        user=user,
        external_id=f"log-{on}-{hour}",
        local_date=on,
        started_at=started,
        ended_at=started + timedelta(minutes=minutes + 20),
        duration_minutes=minutes,
        efficiency=efficiency,
    )


class TestNeighbours:
    """The arrows on the night page. Each one must land on a night that exists."""

    def test_skips_the_nights_that_were_never_recorded(self, owner):
        """Paging by the calendar would step onto a 404 whenever the watch was
        off - which is precisely the gap someone is trying to page over."""
        a_night(owner, NIGHT, minutes=450)
        a_night(owner, NIGHT - timedelta(days=4), minutes=450)
        a_night(owner, NIGHT + timedelta(days=3), minutes=450)

        result = nights.neighbours(owner, NIGHT)
        assert result["previous"] == NIGHT - timedelta(days=4)
        assert result["next"] == NIGHT + timedelta(days=3)

    def test_the_ends_have_nowhere_to_go(self, owner):
        a_night(owner, NIGHT, minutes=450)

        result = nights.neighbours(owner, NIGHT)
        assert result["previous"] is None
        assert result["next"] is None
        assert result["latest"] == NIGHT

    def test_latest_is_the_newest_night_not_this_one(self, owner):
        """The "Last night" tab links here, so on an older page it has to point
        forward - otherwise it links to the page already open and does nothing."""
        a_night(owner, NIGHT, minutes=450)
        a_night(owner, NIGHT + timedelta(days=2), minutes=450)

        assert nights.neighbours(owner, NIGHT)["latest"] == NIGHT + timedelta(days=2)

    def test_another_users_nights_are_not_stepped_onto(self, owner, db):
        other = User.objects.create_user(username="other-neighbour", password=PASSWORD)
        a_night(owner, NIGHT, minutes=450)
        a_night(other, NIGHT - timedelta(days=1), minutes=450)

        assert nights.neighbours(owner, NIGHT)["previous"] is None


class TestBaseline:
    def test_averages_only_recorded_nights(self, owner):
        """A watch on the charger is a missing measurement. Counting the gaps
        as nights of no sleep invents a decline that never happened."""
        for offset in range(1, 8):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450)

        result = nights.baseline(owner, NIGHT)
        assert result["nights_recorded"] == 7
        assert result["mean_duration_minutes"] == 450

    def test_too_few_nights_is_no_average_at_all(self, owner):
        """Two nights is not a personal norm, and "38 minutes above your
        average" computed from two nights is false authority."""
        for offset in (1, 2):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450)

        assert nights.baseline(owner, NIGHT)["mean_duration_minutes"] is None

    def test_the_night_itself_is_not_in_its_own_baseline(self, owner):
        a_night(owner, NIGHT, minutes=200)
        for offset in range(1, 8):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450)

        assert nights.baseline(owner, NIGHT)["mean_duration_minutes"] == 450


class TestVerdict:
    def build(self, owner, *, minutes: int, efficiency: int) -> dict:
        session = a_night(owner, NIGHT, minutes=minutes, efficiency=efficiency)
        for offset in range(1, 8):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450)
        return nights.verdict(session, nights.baseline(owner, NIGHT), nights.oxygen([]))

    def test_short_but_efficient_names_the_schedule(self, owner):
        """The distinction the whole sentence exists for: too little time in
        bed and too little sleep in the time look identical in a duration."""
        result = self.build(owner, minutes=330, efficiency=94)
        assert result["headline"] == "Good sleep, but short"
        assert "time in bed" in result["detail"]

    def test_enough_time_in_bed_but_restless(self, owner):
        result = self.build(owner, minutes=440, efficiency=68)
        assert result["headline"] == "Enough time in bed, restless in it"

    def test_on_target_and_efficient_is_a_good_night(self, owner):
        result = self.build(owner, minutes=455, efficiency=93)
        assert result["headline"] == "A good night"

    def test_the_delta_against_the_baseline_is_stated(self, owner):
        result = self.build(owner, minutes=390, efficiency=90)
        assert result["delta_minutes"] == -60
        assert "1h 00m below your 30-day average" in result["detail"]

    def test_a_delta_too_small_to_matter_is_not_mentioned(self, owner):
        result = self.build(owner, minutes=455, efficiency=93)
        assert "average" not in result["detail"]

    def test_oxygen_never_sets_the_headline(self, owner):
        """A wrist SpO2 estimate is not grounds for leading a health page with
        alarm - it is appended, and the duration story still comes first."""
        session = a_night(owner, NIGHT, minutes=455, efficiency=93)
        low = nights.oxygen(minutes([96.0] * 30 + [86.0] * 4 + [96.0] * 30))
        result = nights.verdict(session, nights.baseline(owner, NIGHT), low)
        assert result["headline"] == "A good night"
        assert "86%" in result["detail"]


class TestSignals:
    def test_a_stage_share_outside_the_normal_range_is_flagged(self, owner, session):
        stage(session, "light", at=0, minutes=180)
        stage(session, "deep", at=180, minutes=10)
        stage(session, "rem", at=190, minutes=50)
        found = nights.detail(owner, NIGHT)["signals"]
        deep = next(signal for signal in found if signal["key"] == "deep")
        assert deep["state"] == "watch"

    def test_efficiency_states_step_from_ok_to_concern(self, owner):
        for efficiency, expected in ((93, "ok"), (80, "watch"), (60, "concern")):
            SleepSession.objects.filter(user=owner).delete()
            a_night(owner, NIGHT, minutes=450, efficiency=efficiency)
            found = nights.detail(owner, NIGHT)["signals"]
            state = next(s for s in found if s["key"] == "efficiency")["state"]
            assert state == expected


class TestSummary:
    def test_shortfall_is_per_recorded_night_not_cumulative(self, owner):
        """With 7 nights recorded out of 30, a cumulative debt mostly measures
        the 23 nights nobody wore the watch."""
        for offset in range(7):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=420)

        result = nights.summary(owner, start=NIGHT - timedelta(days=29), end=NIGHT)
        assert result["nights_recorded"] == 7
        assert result["days_elapsed"] == 30
        assert result["mean_shortfall_minutes"] == -30

    def test_nights_on_target_allows_the_tolerance(self, owner):
        a_night(owner, NIGHT, minutes=425)
        a_night(owner, NIGHT - timedelta(days=1), minutes=415)

        result = nights.summary(owner, start=NIGHT - timedelta(days=6), end=NIGHT)
        assert result["nights_on_target"] == 1

    def test_no_comparison_without_enough_nights_on_both_sides(self, owner):
        for offset in range(7):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450)

        result = nights.summary(owner, start=NIGHT - timedelta(days=6), end=NIGHT)
        assert result["previous"]["comparable"] is False
        assert result["previous"]["duration_delta_minutes"] is None

    def test_what_changed_against_the_preceding_window(self, owner):
        for offset in range(7):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=460)
        for offset in range(7, 14):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=400)

        result = nights.summary(owner, start=NIGHT - timedelta(days=6), end=NIGHT)
        assert result["previous"]["comparable"] is True
        assert result["previous"]["duration_delta_minutes"] == 60


class TestBedtimeSpread:
    def test_a_regular_bedtime_has_a_small_spread(self, owner):
        for offset in range(7):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450, hour=12)
        result = nights.summary(owner, start=NIGHT - timedelta(days=6), end=NIGHT)
        assert result["bedtime_spread_minutes"] == 0

    def test_bedtimes_either_side_of_midnight_are_close_together(self, owner):
        """Clock time wraps. 23:50 and 00:10 are twenty minutes apart, and
        arithmetic on the raw numbers calls them twenty-three hours apart -
        which would report the most regular sleeper alive as chaotic."""
        for offset in range(4):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450, hour=13)
        for offset in range(4, 8):
            a_night(owner, NIGHT - timedelta(days=offset), minutes=450, hour=14)

        result = nights.summary(owner, start=NIGHT - timedelta(days=7), end=NIGHT)
        assert result["bedtime_spread_minutes"] is not None
        assert result["bedtime_spread_minutes"] < 45
