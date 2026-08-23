"""Office days: the portal's mark/unmark toggle.

The property worth pinning is that (created_by, local_date) is unique
regardless of `deleted_at` (see `OfficeDay`), so unmarking then re-marking the
same day must update that one tombstoned row rather than collide with its own
unique constraint on a second insert.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.health.models import DailyMetric, OfficeDay

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


def test_marking_a_day_creates_it(alex, client_for):
    response = client_for(alex).put("/api/v1/health/office/days/2026-08-19")

    assert response.status_code == 200
    assert response.json() == {"local_date": "2026-08-19", "worked": True}
    row = OfficeDay.objects.get(created_by=alex, local_date=date(2026, 8, 19))
    assert row.deleted_at is None


def test_unmarking_tombstones_rather_than_deletes(alex, client_for):
    client_for(alex).put("/api/v1/health/office/days/2026-08-19")

    response = client_for(alex).delete("/api/v1/health/office/days/2026-08-19")

    assert response.status_code == 200
    assert response.json() == {"local_date": "2026-08-19", "worked": False}
    row = OfficeDay.objects.get(created_by=alex, local_date=date(2026, 8, 19))
    assert row.deleted_at is not None


def test_remarking_a_tombstoned_day_reuses_the_row(alex, client_for):
    client_for(alex).put("/api/v1/health/office/days/2026-08-19")
    client_for(alex).delete("/api/v1/health/office/days/2026-08-19")

    response = client_for(alex).put("/api/v1/health/office/days/2026-08-19")

    assert response.status_code == 200
    assert response.json()["worked"] is True
    assert OfficeDay.objects.filter(created_by=alex, local_date=date(2026, 8, 19)).count() == 1


def test_a_marked_day_shows_up_in_the_report(alex, client_for):
    client_for(alex).put("/api/v1/health/office/days/2026-08-19")

    response = client_for(alex).get("/api/v1/health/office?year=2026")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["days"] == ["2026-08-19"]


def _metric(user, on: date, metric: str, value: float) -> None:
    DailyMetric.objects.create(
        user=user, local_date=on, metric=metric, value=value, source=DailyMetric.Source.DEVICE
    )


def test_wfh_report_buckets_by_day_type(alex, client_for):
    today = date.today()
    window = [today - timedelta(days=n) for n in range(14)]
    weekdays = sorted((d for d in window if d.weekday() < 5), reverse=True)
    weekends = [d for d in window if d.weekday() >= 5]
    assert len(weekdays) >= 4
    assert len(weekends) >= 1

    # Two office days bound the coverage range so the wfh days in between
    # fall inside it rather than being excluded as "unknown".
    office_a, wfh_a, wfh_b, office_b = weekdays[0], weekdays[1], weekdays[2], weekdays[-1]
    weekend_day = weekends[0]

    for on in (office_a, office_b):
        client_for(alex).put(f"/api/v1/health/office/days/{on.isoformat()}")

    for on, value in ((office_a, 9000), (office_b, 9000)):
        _metric(alex, on, "steps", value)
    for on, value in ((wfh_a, 4000), (wfh_b, 5000)):
        _metric(alex, on, "steps", value)
    _metric(alex, weekend_day, "steps", 8000)

    response = client_for(alex).get("/api/v1/health/office/report?days=14")

    assert response.status_code == 200
    body = response.json()
    assert body["days"]["office"] == 2
    # Every weekday inside the coverage range that isn't marked "office" is
    # "wfh" - not just the two with a steps reading logged.
    assert body["days"]["wfh"] == len(weekdays) - 2
    assert body["days"]["weekend"] >= 1

    steps = next(m for m in body["metrics"] if m["metric"] == "steps")
    assert steps["office"] == 9000
    assert steps["wfh"] == 4500
    assert steps["weekend"] == 8000
    assert steps["direction"] == "up"
    assert steps["office_days"] == 2
    assert steps["wfh_days"] == 2


def test_wfh_report_skips_metrics_with_only_one_bucket(alex, client_for):
    today = date.today()
    weekdays = sorted(d for d in (today - timedelta(days=n) for n in range(14)) if d.weekday() < 5)
    office_a, office_b = weekdays[0], weekdays[-1]
    for on in (office_a, office_b):
        client_for(alex).put(f"/api/v1/health/office/days/{on.isoformat()}")
    _metric(alex, office_a, "resting_hr", 60)
    _metric(alex, office_b, "resting_hr", 62)

    response = client_for(alex).get("/api/v1/health/office/report?days=14")

    assert response.status_code == 200
    keys = [m["metric"] for m in response.json()["metrics"]]
    assert "resting_hr" not in keys


def test_wfh_report_excludes_weekdays_outside_office_coverage(alex, client_for):
    today = date.today()
    weekday = next(d for d in (today - timedelta(days=n) for n in range(30)) if d.weekday() < 5)
    _metric(alex, weekday, "steps", 5000)

    response = client_for(alex).get("/api/v1/health/office/report?days=30")

    assert response.status_code == 200
    body = response.json()
    # No office days recorded at all, so every weekday is unclassifiable.
    assert body["days"]["wfh"] == 0
    assert body["days"]["office"] == 0
    assert body["days"]["excluded"] > 0
