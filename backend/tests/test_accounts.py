from __future__ import annotations

import pytest

from apps.accounts.models import User

PASSWORD = "x" * 8


@pytest.mark.django_db
def test_signup_accepts_a_short_simple_password():
    """No AUTH_PASSWORD_VALIDATORS - `admin`/`admin` must work."""
    from django.test import Client

    client = Client()
    resp = client.post(
        "/api/v1/auth/signup",
        data={"username": "admin", "password": "admin", "birth_date": "1990-05-15", "sex": ""},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["username"] == "admin"
    assert User.objects.get(username="admin").check_password("admin")


@pytest.mark.django_db
def test_signup_rejects_a_duplicate_username(user):
    from django.test import Client

    client = Client()
    resp = client.post(
        "/api/v1/auth/signup",
        data={
            "username": user.username,
            "password": PASSWORD,
            "birth_date": "1991-01-01",
            "sex": "",
        },
        content_type="application/json",
    )
    assert resp.status_code == 409


@pytest.mark.django_db
def test_login_then_me_round_trips(user):
    from django.test import Client

    client = Client()
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )
    assert resp.status_code == 200

    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == user.username


@pytest.mark.django_db
def test_login_rejects_wrong_password(user):
    from django.test import Client

    client = Client()
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": user.username, "password": "not-it"},
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_me_requires_authentication():
    from django.test import Client

    resp = Client().get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_age_years_accounts_for_birthday_not_yet_reached(user):
    from datetime import date

    from django.utils import timezone

    today = timezone.localdate()
    # A birth_date whose month/day is one day after today: the birthday this
    # year hasn't happened yet, so age_years must subtract one more year than
    # a naive year-subtraction would.
    not_yet = date(today.year - 30, today.month, today.day) + timezone.timedelta(days=1)
    user.birth_date = not_yet
    user.save(update_fields=["birth_date"])
    assert user.age_years == 29
