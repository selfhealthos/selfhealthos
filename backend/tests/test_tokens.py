from __future__ import annotations

import pytest

from apps.tokens.models import AccessToken

PASSWORD = "x" * 8


@pytest.mark.django_db
def test_create_list_and_revoke_token(user, client_for):
    client = client_for(user)

    resp = client.post(
        "/api/v1/tokens",
        data={"name": "Claude Code", "preset": "claude", "kind": "agent"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["scopes"] == ["health:read"]
    assert body["secret"].startswith("shos_pat_")
    token_id = body["id"]

    resp = client.get("/api/v1/tokens")
    assert resp.status_code == 200
    assert [t["id"] for t in resp.json()] == [token_id]

    resp = client.delete(f"/api/v1/tokens/{token_id}")
    assert resp.status_code == 204
    assert AccessToken.objects.get(pk=token_id).revoked_at is not None


@pytest.mark.django_db
def test_bearer_token_authenticates_without_a_session(user, client_for):
    from django.test import Client

    secret = AccessToken.issue(user=user, name="script", scopes=["health:read"])[1]

    resp = Client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {secret}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == user.username


@pytest.mark.django_db
def test_revoked_token_no_longer_authenticates(user):
    from django.test import Client

    token, secret = AccessToken.issue(user=user, name="script", scopes=["health:read"])
    token.revoke()

    resp = Client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {secret}"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_enrol_trades_username_and_password_for_a_token(user):
    from django.test import Client

    resp = Client().post(
        "/api/v1/tokens/enrol",
        data={
            "username": user.username,
            "password": PASSWORD,
            "device_name": "My phone",
            "preset": "full-access",
        },
        content_type="application/json",
    )
    assert resp.status_code == 201
    # Spelled out rather than compared against PRESETS: the point is to notice
    # when a preset's grant widens, which a comparison against the definition
    # would silently agree with.
    assert set(resp.json()["scopes"]) == {
        "health:read",
        "health:write",
        "social:read",
        "social:write",
    }
