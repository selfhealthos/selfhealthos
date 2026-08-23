"""The health REST surface.

Scoping is the thing worth testing hardest: every endpoint answers for the
logged-in user, and unlike the shared-library apps a second person's numbers
must never appear in the first person's chart.
"""

from datetime import UTC, date, datetime

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.health.models import DailyMetric, DietEntry, Habit, HabitCompletion, Sample, SleepSession

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    # Non-UTC, so a local day is not a UTC day and the difference shows in
    # day-boundary assertions below.
    return User.objects.create_user(
        username="alex", password=PASSWORD, timezone="Australia/Melbourne"
    )


@pytest.fixture
def sam(db):
    return User.objects.create_user(username="sam", password=PASSWORD)


@pytest.fixture
def client_for():
    def _make(user):
        client = Client()
        client.force_login(user)
        return client

    return _make


def seed(user, *, day=date(2026, 6, 4), steps=9811.0):
    DailyMetric.objects.create(
        user=user,
        local_date=day,
        metric="steps",
        value=steps,
        source=DailyMetric.Source.DEVICE,
    )
    DailyMetric.objects.create(
        user=user,
        local_date=day,
        metric="resting_hr",
        value=64.0,
        source=DailyMetric.Source.DEVICE,
    )
    DietEntry.objects.create(
        created_by=user,
        name="apple",
        occurred_at=datetime(2026, 6, 3, 22, 0, tzinfo=UTC),
        local_date=day,
    )
    habit = Habit.objects.create(created_by=user, name="magnesium", sort_order=0)
    Habit.objects.create(created_by=user, name="psyllium husk", sort_order=1)
    HabitCompletion.objects.create(
        created_by=user,
        habit=habit,
        habit_name="magnesium",
        local_date=day,
    )
    SleepSession.objects.create(
        user=user,
        external_id="s1",
        local_date=day,
        started_at=datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 3, 19, 0, tzinfo=UTC),
        duration_minutes=419,
        efficiency=86,
        minutes_deep=59,
        minutes_light=244,
        minutes_rem=55,
        minutes_awake=59,
        awakenings_count=0,
    )
    return day


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------


def test_every_endpoint_refuses_an_anonymous_caller(db):
    anon = Client()
    for path in [
        "/api/v1/health/summary",
        "/api/v1/health/metrics",
        "/api/v1/health/today",
        "/api/v1/health/days/2026-06-04",
        "/api/v1/health/trend?metric=steps",
        "/api/v1/health/intraday?metric=hr&on=2026-06-04",
    ]:
        assert anon.get(path).status_code == 401, path


def test_one_persons_data_never_appears_in_anothers(alex, sam, client_for):
    day = seed(alex, steps=9811.0)
    seed(sam, steps=1.0)

    payload = client_for(sam).get(f"/api/v1/health/days/{day}").json()

    assert payload["metrics"]["steps"] == 1.0
    assert payload["diet"] == [] or all(d["name"] == "apple" for d in payload["diet"])
    assert len(payload["diet"]) == 1  # sam's own, not sam's plus alex's


def test_trend_is_scoped_to_the_caller(alex, sam, client_for):
    seed(alex, steps=9811.0)
    seed(sam, steps=1.0)

    payload = (
        client_for(sam)
        .get("/api/v1/health/trend?metric=steps&start=2026-06-01&end=2026-06-30")
        .json()
    )

    assert [p["value"] for p in payload["points"]] == [1.0]


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_summary_reports_coverage(alex, client_for):
    seed(alex)

    payload = client_for(alex).get("/api/v1/health/summary").json()

    assert payload["first_date"] == "2026-06-04"
    assert payload["entries"]["diet"] == 1
    assert payload["metrics"]["steps"]["days"] == 1


def test_metric_catalogue_is_the_vocabulary(alex, client_for):
    payload = client_for(alex).get("/api/v1/health/metrics").json()

    keys = {m["key"] for m in payload}
    assert {"steps", "resting_hr", "sleep_minutes", "bristol_mean"} <= keys
    resting = next(m for m in payload if m["key"] == "resting_hr")
    assert resting["unit"] == "bpm"
    assert resting["description"]


def test_day_lists_habits_missed_as_well_as_done(alex, client_for):
    """A list of completions cannot answer "what did I miss"."""
    day = seed(alex)

    payload = client_for(alex).get(f"/api/v1/health/days/{day}").json()

    habits = {h["name"]: h["completed"] for h in payload["habits"]}
    assert habits == {"magnesium": True, "psyllium husk": False}


def test_a_habit_is_ticked_despite_differing_capitalisation(alex, client_for):
    """The archive holds habits whose completions differ from the habit name by
    case alone. An exact string match reports those as missed every day."""
    day = seed(alex)
    Habit.objects.create(created_by=alex, name="Sauna", sort_order=2)
    HabitCompletion.objects.create(
        created_by=alex,
        habit_name="sauna",
        local_date=day,
    )

    payload = client_for(alex).get(f"/api/v1/health/days/{day}").json()

    assert {h["name"]: h["completed"] for h in payload["habits"]}["Sauna"] is True


def test_day_reports_the_timezone_it_filed_entries_under(alex, client_for):
    """A server-rendered page runs in UTC; without this it formats a 7:36am
    coffee as 9:36pm the day before."""
    day = seed(alex)

    payload = client_for(alex).get(f"/api/v1/health/days/{day}").json()

    assert payload["timezone"] == "Australia/Melbourne"


def test_day_includes_sleep_and_metrics(alex, client_for):
    day = seed(alex)

    payload = client_for(alex).get(f"/api/v1/health/days/{day}").json()

    assert payload["sleep"]["duration_minutes"] == 419
    assert payload["sleep"]["efficiency"] == 86
    assert payload["metrics"]["resting_hr"] == 64.0


def test_today_falls_back_to_the_latest_day_with_data(alex, client_for):
    """Opening the dashboard before the watch has synced should not show an
    empty page."""
    day = seed(alex)

    payload = client_for(alex).get("/api/v1/health/today").json()

    assert payload["date"] == day.isoformat()


def test_an_empty_day_is_a_200_not_a_404(alex, client_for):
    seed(alex)

    response = client_for(alex).get("/api/v1/health/days/2020-01-01")

    assert response.status_code == 200
    assert response.json()["metrics"] == {}


def test_trend_moving_average_waits_for_a_full_window(alex, client_for):
    for offset, value in enumerate([10.0, 20.0, 30.0]):
        DailyMetric.objects.create(
            user=alex, local_date=date(2026, 6, 1 + offset), metric="steps", value=value
        )

    payload = (
        client_for(alex)
        .get("/api/v1/health/trend?metric=steps&start=2026-06-01&end=2026-06-03&window=3")
        .json()
    )

    assert [p["average"] for p in payload["points"]] == [None, None, 20.0]
    assert payload["mean"] == 20.0
    assert payload["unit"] == "count"


def test_an_unknown_metric_is_a_client_error(alex, client_for):
    response = client_for(alex).get("/api/v1/health/trend?metric=not_a_metric")

    assert response.status_code == 400


def test_intraday_returns_a_local_day_of_samples(alex, client_for):
    # 08:00 and 08:01 Melbourne on 4 June is 22:00/22:01 UTC on 3 June.
    for minute, value in [(0, 89.5), (1, 92.0)]:
        Sample.objects.create(
            user=alex,
            metric="hr",
            ts=datetime(2026, 6, 3, 22, minute, tzinfo=UTC),
            value=value,
        )
    # A sample just outside the local day must not be included.
    Sample.objects.create(
        user=alex, metric="hr", ts=datetime(2026, 6, 4, 14, 1, tzinfo=UTC), value=999.0
    )

    payload = client_for(alex).get("/api/v1/health/intraday?metric=hr&on=2026-06-04").json()

    assert payload["count"] == 2
    assert payload["maximum"] == 92.0
    assert [p["value"] for p in payload["points"]] == [89.5, 92.0]


def test_a_metric_with_no_intraday_series_is_refused(alex, client_for):
    response = client_for(alex).get("/api/v1/health/intraday?metric=sleep_efficiency&on=2026-06-04")

    assert response.status_code == 400
