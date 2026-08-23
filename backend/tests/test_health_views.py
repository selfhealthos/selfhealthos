"""The deep-dive Health views.

What is pinned here is what looks correct and is not: a streak that reads zero
every morning, a habit reported as missed all year because its completions
capitalise its name differently, a note rendered as raw block JSON, and a lab
marker split into three one-point series by three spellings of the same word.
Every one of those produces a page that renders without error and lies.

Scoping is tested on each endpoint for the same reason it is in
`test_health_api.py`: unlike the shared-library apps, a second person's numbers
must never reach the first person's page.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.health import services
from apps.health.models import (
    BmEntry,
    BodyMeasurement,
    DietEntry,
    Doc,
    ExerciseEntry,
    Habit,
    HabitCompletion,
    LabResult,
    Note,
    OfficeDay,
    SleepSession,
)

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    return User.objects.create_user(username="alex", password=PASSWORD)


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


@pytest.fixture
def today(alex):
    """The user's own local today - every service function reads this."""
    from apps.health import timeutils

    return timeutils.local_date_of(timezone.now(), timeutils.tz_for(alex))


def noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Habits
# --------------------------------------------------------------------------


def test_streak_survives_a_today_that_is_not_ticked_yet(alex, today):
    """The bug the dashboard shipped: an intact streak reads zero each morning.

    Someone opens this at 8am, before the box is checked. Counting back from
    today finds nothing and reports 0, wiping a run that is still going.
    """
    habit = Habit.objects.create(created_by=alex, name="Magnesium")
    for offset in range(1, 6):  # yesterday back through five days ago
        HabitCompletion.objects.create(
            created_by=alex,
            habit=habit,
            habit_name="Magnesium",
            local_date=today - timedelta(days=offset),
        )

    row = services.habit_history(alex, days=30)["habits"][0]
    assert row["current_streak"] == 5
    assert row["best_streak"] == 5


def test_streak_breaks_on_a_genuinely_missed_day(alex, today):
    habit = Habit.objects.create(created_by=alex, name="Walk")
    for offset in (1, 2, 5, 6, 7):
        HabitCompletion.objects.create(
            created_by=alex,
            habit=habit,
            habit_name="Walk",
            local_date=today - timedelta(days=offset),
        )

    row = services.habit_history(alex, days=30)["habits"][0]
    assert row["current_streak"] == 2
    assert row["best_streak"] == 3


def test_grid_matches_a_completion_whose_name_differs_only_in_case(alex, today):
    """The archive holds "magnesium" ticks against a habit named "Magnesium".

    An exact string match reports every one of them as missed, so the grid is a
    year of empty cells for a habit that was never skipped.
    """
    Habit.objects.create(created_by=alex, name="Magnesium")
    HabitCompletion.objects.create(
        created_by=alex,
        habit=None,
        habit_name="magnesium ",
        local_date=today,
    )

    history = services.habit_history(alex, days=7)
    row = history["habits"][0]
    assert row["completed"][history["dates"].index(today)] is True
    assert row["total"] == 1


def test_habit_grid_row_lines_up_with_the_dates(alex, today):
    """`completed` is a parallel array; a length mismatch silently shifts it."""
    Habit.objects.create(created_by=alex, name="Water")
    history = services.habit_history(alex, days=14)
    assert len(history["dates"]) == 14
    assert history["dates"][-1] == today
    assert len(history["habits"][0]["completed"]) == 14


def test_habits_endpoint_is_scoped_to_the_caller(alex, sam, client_for):
    Habit.objects.create(created_by=sam, name="Sam's habit")
    body = client_for(alex).get("/api/v1/health/habits?days=7").json()
    assert body["habits"] == []


# --------------------------------------------------------------------------
# Diet
# --------------------------------------------------------------------------


def test_food_flags_are_applied_at_read_time(alex, today):
    DietEntry.objects.create(
        created_by=alex, name="flat white with milk", occurred_at=noon(today), local_date=today
    )
    log = services.diet_log(alex, days=7)
    flags = log["entries"][0]["flags"]
    assert "caffeine" in flags
    assert "dairy" in flags
    assert log["caffeine"][0]["name"] == "flat white with milk"


def test_top_foods_count_the_window_not_the_search_results(alex, today):
    """ "Most eaten" must not quietly mean "most eaten among what you searched"."""
    for _ in range(3):
        DietEntry.objects.create(
            created_by=alex, name="porridge", occurred_at=noon(today), local_date=today
        )
    DietEntry.objects.create(
        created_by=alex, name="banana", occurred_at=noon(today), local_date=today
    )

    log = services.diet_log(alex, days=7, search="banana")
    assert [e["name"] for e in log["entries"]] == ["banana"]
    assert log["top"][0] == {"name": "porridge", "count": 3}


def test_diet_endpoint_is_scoped_to_the_caller(alex, sam, client_for, today):
    DietEntry.objects.create(
        created_by=sam, name="sam's toast", occurred_at=noon(today), local_date=today
    )
    body = client_for(alex).get("/api/v1/health/diet?days=7").json()
    assert body["entries"] == []
    assert body["top"] == []


# --------------------------------------------------------------------------
# Gut
# --------------------------------------------------------------------------


def test_suspects_report_how_often_a_food_was_eaten_at_all(alex, today):
    """Without `days_eaten` the table indicts breakfast.

    Porridge precedes both bad days and is eaten every day; chocolate precedes
    both and is eaten only on those days. Both score 2 on bad days, so the
    denominator is the only thing that separates them.
    """
    bad_days = [today - timedelta(days=3), today - timedelta(days=1)]
    for day in bad_days:
        BmEntry.objects.create(created_by=alex, bristol=7, occurred_at=noon(day), local_date=day)
        DietEntry.objects.create(
            created_by=alex, name="chocolate", occurred_at=noon(day), local_date=day
        )
    for offset in range(6):
        day = today - timedelta(days=offset)
        DietEntry.objects.create(
            created_by=alex, name="porridge", occurred_at=noon(day), local_date=day
        )

    suspects = {row["name"]: row for row in services.gut_detail(alex, days=14)["suspects"]}
    assert suspects["chocolate"]["before_bad_days"] == 2
    assert suspects["chocolate"]["days_eaten"] == 2
    assert suspects["porridge"]["before_bad_days"] == 2
    assert suspects["porridge"]["days_eaten"] == 6
    assert suspects["chocolate"]["share"] > suspects["porridge"]["share"]


def test_bad_day_foods_include_the_day_before(alex, today):
    """ "Precede" means the day before as well - that is the actionable window."""
    bad = today - timedelta(days=1)
    BmEntry.objects.create(created_by=alex, bristol=6, occurred_at=noon(bad), local_date=bad)
    DietEntry.objects.create(
        created_by=alex,
        name="late curry",
        occurred_at=noon(bad - timedelta(days=1)),
        local_date=bad - timedelta(days=1),
    )

    bad_days = services.gut_detail(alex, days=14)["bad_days"]
    assert bad_days[0]["foods"] == ["late curry"]


def test_bristol_daily_counts_each_score_separately(alex, today):
    """The stacked column needs "two 4s and a 6", which is three numbers.

    `DailyMetric` holds one scalar per metric per day, so this cannot come from
    the rollup without seven new keys in a vocabulary that is a public
    contract.
    """
    for score in (4, 4, 6):
        BmEntry.objects.create(
            created_by=alex, bristol=score, occurred_at=noon(today), local_date=today
        )

    point = services.bristol_daily(alex, days=7)["points"][0]
    assert point["date"] == today
    assert point["counts"] == [0, 0, 0, 2, 0, 1, 0]
    assert point["total"] == 3


def test_bristol_daily_omits_days_with_nothing_recorded(alex, today):
    """A gap is honest; a zero column asserts that nothing happened."""
    day = today - timedelta(days=2)
    BmEntry.objects.create(created_by=alex, bristol=3, occurred_at=noon(day), local_date=day)

    points = services.bristol_daily(alex, days=7)["points"]
    assert [p["date"] for p in points] == [day]


def test_bristol_daily_is_scoped_to_the_caller(alex, sam, client_for, today):
    BmEntry.objects.create(created_by=sam, bristol=5, occurred_at=noon(today), local_date=today)
    assert client_for(alex).get("/api/v1/health/bristol?days=7").json()["points"] == []


def test_a_normal_bristol_score_is_not_a_bad_day(alex, today):
    BmEntry.objects.create(created_by=alex, bristol=4, occurred_at=noon(today), local_date=today)
    detail = services.gut_detail(alex, days=7)
    assert detail["bad_day_count"] == 0
    assert detail["distribution"][3] == {"bristol": 4, "count": 1}


# --------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------


def test_block_json_notes_are_flattened_to_text(alex, today):
    """The Android app changed format mid-history and did not migrate.

    Rendering `content` verbatim shows a wall of JSON for every older note.
    """
    Note.objects.create(
        created_by=alex,
        title="Checkup",
        content='[{"t":"text","v":"BP was fine."},{"t":"todo","v":"ignore me"},'
        '{"t":"text","v":"Back in June."}]',
        occurred_at=noon(today),
        local_date=today,
    )
    note = services.note_list(alex)[0]
    assert note["body"] == "BP was fine.\nBack in June."


def test_a_plain_text_note_is_left_alone(alex, today):
    Note.objects.create(
        created_by=alex, title="", content="Just text.", occurred_at=noon(today), local_date=today
    )
    assert services.note_list(alex)[0]["body"] == "Just text."


def test_a_note_that_only_looks_like_block_json_is_shown_verbatim(alex, today):
    """Better to show the text than to swallow it because it opens with "["."""
    Note.objects.create(
        created_by=alex,
        title="",
        content="[not actually json",
        occurred_at=noon(today),
        local_date=today,
    )
    assert services.note_list(alex)[0]["body"] == "[not actually json"


def test_note_search_reaches_content_inside_the_block_format(alex, today):
    Note.objects.create(
        created_by=alex,
        title="Untitled",
        content='[{"t":"text","v":"cholesterol result"}]',
        occurred_at=noon(today),
        local_date=today,
    )
    assert len(services.note_list(alex, search="cholesterol")) == 1
    assert services.note_list(alex, search="nothing here") == []


def test_notes_endpoint_is_scoped_to_the_caller(alex, sam, client_for, today):
    Note.objects.create(
        created_by=sam, title="Sam", content="private", occurred_at=noon(today), local_date=today
    )
    assert client_for(alex).get("/api/v1/health/notes").json() == []


# --------------------------------------------------------------------------
# Labs
# --------------------------------------------------------------------------


def test_markers_group_across_spellings_of_the_same_name(alex, today):
    """`marker_name` is free text typed on a phone.

    Grouping on the raw string draws three one-point charts where there is one
    marker with three readings.
    """
    for offset, (name, value) in enumerate((("HDL", 1.1), ("hdl", 1.3), ("Hdl ", 1.2))):
        LabResult.objects.create(
            created_by=alex,
            marker_name=name,
            value=value,
            unit="mmol/L",
            taken_on=today - timedelta(days=offset * 30),
        )

    markers = services.lab_history(alex)
    assert len(markers) == 1
    marker = markers[0]
    assert marker["count"] == 3
    # The newest spelling is the one on display, and the newest value is the
    # headline - both read off the same row.
    assert marker["name"] == "HDL"
    assert marker["latest_value"] == 1.1
    assert (marker["minimum"], marker["maximum"]) == (1.1, 1.3)
    # Oldest first, because this is what a chart plots.
    assert [r["value"] for r in marker["results"]] == [1.2, 1.3, 1.1]


def test_labs_endpoint_is_scoped_to_the_caller(alex, sam, client_for, today):
    LabResult.objects.create(created_by=sam, marker_name="LDL", value=3.0, taken_on=today)
    assert client_for(alex).get("/api/v1/health/labs").json() == []


# --------------------------------------------------------------------------
# Body, office days, sleep, activity
# --------------------------------------------------------------------------


def test_body_history_carries_height_so_the_ratio_is_derivable(alex, today):
    from apps.health.models import Profile

    Profile.objects.create(user=alex, height_cm=185.0)
    BodyMeasurement.objects.create(
        created_by=alex, waist_cm=92.0, occurred_at=noon(today), local_date=today
    )
    body = services.body_history(alex, days=90)
    assert body["height_cm"] == 185.0
    assert body["measurements"][0]["waist_cm"] == 92.0


def test_body_history_reports_no_height_rather_than_guessing_one(alex, today):
    BodyMeasurement.objects.create(
        created_by=alex, waist_cm=92.0, occurred_at=noon(today), local_date=today
    )
    assert services.body_history(alex, days=90)["height_cm"] is None


def test_office_days_report_the_bounds_of_what_is_known(alex):
    """Absence means unknown, not work-from-home - so the range has to travel.

    Without it a blank January reads as "never went in" rather than "the record
    starts in March".
    """
    for day in (date(2026, 3, 2), date(2026, 3, 4), date(2026, 7, 1)):
        OfficeDay.objects.create(created_by=alex, local_date=day)

    office = services.office_days(alex, year=2026)
    assert office["total"] == 3
    assert office["covers_from"] == date(2026, 3, 2)
    assert office["covers_to"] == date(2026, 7, 1)
    assert office["by_month"][2] == {"month": 3, "count": 2}
    assert office["by_month"][0] == {"month": 1, "count": 0}
    assert office["years"] == [2026]


def test_sleep_history_excludes_naps(alex, today):
    """A 20-minute afternoon nap listed beside a 7-hour night is noise."""
    for is_main, minutes in ((True, 430), (False, 22)):
        SleepSession.objects.create(
            user=alex,
            external_id=f"s{minutes}",
            local_date=today,
            started_at=noon(today),
            ended_at=noon(today) + timedelta(minutes=minutes),
            duration_minutes=minutes,
            is_main_sleep=is_main,
        )

    sessions = services.sleep_history(alex, days=7)["sessions"]
    assert [s["duration_minutes"] for s in sessions] == [430]


def test_activity_buckets_weeks_from_monday(alex):
    """A week here has to be the week everyone else means."""
    # 2026-06-03 is a Wednesday; 2026-06-08 the following Monday.
    for day, seconds in ((date(2026, 6, 3), 1_800), (date(2026, 6, 8), 600)):
        ExerciseEntry.objects.create(
            created_by=alex,
            video_name="Yoga",
            duration_s=seconds,
            occurred_at=noon(day),
            local_date=day,
        )

    detail = services.activity_detail(alex, days=3_000)
    weeks = {row["week"]: row for row in detail["weekly"]}
    assert weeks[date(2026, 6, 1)]["minutes"] == 30.0
    assert weeks[date(2026, 6, 8)]["minutes"] == 10.0
    assert detail["by_type"][0] == {"name": "Yoga", "count": 2, "minutes": 40.0}


def test_docs_endpoint_reports_a_row_with_no_image(alex, client_for, today):
    """`photo_path` is an on-device path; the file may never have been backfilled.

    The row is still worth showing - the date and title are the useful part.
    """
    Doc.objects.create(
        created_by=alex,
        title="Pathology 2026-06",
        photo_path="/storage/emulated/0/DCIM/x.jpg",
        occurred_at=noon(today),
        local_date=today,
    )
    body = client_for(alex).get("/api/v1/health/docs").json()
    assert body[0]["title"] == "Pathology 2026-06"
    assert body[0]["image_url"] is None


# --------------------------------------------------------------------------
# Batched trends
# --------------------------------------------------------------------------


def test_trends_skips_an_unknown_metric_instead_of_failing_the_page(alex, client_for):
    """The caller is a layout asking for what it would like to draw.

    A metric this archive never held should leave a gap, not a 400 where the
    page was.
    """
    response = client_for(alex).get("/api/v1/health/trends?metrics=steps,not_a_metric,resting_hr")
    assert response.status_code == 200
    assert [t["metric"] for t in response.json()] == ["steps", "resting_hr"]


def test_trends_returns_the_same_shape_as_the_single_trend(alex, client_for):
    from apps.health.models import DailyMetric

    DailyMetric.objects.create(
        user=alex, local_date=date(2026, 6, 4), metric="steps", value=9_811.0
    )
    query = "metrics=steps&start=2026-06-01&end=2026-06-04"
    batched = client_for(alex).get(f"/api/v1/health/trends?{query}").json()[0]
    single = (
        client_for(alex)
        .get("/api/v1/health/trend?metric=steps&start=2026-06-01&end=2026-06-04")
        .json()
    )
    assert batched == single
