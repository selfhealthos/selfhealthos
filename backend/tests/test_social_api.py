"""The social REST surface.

`test_social.py` pins the graph's rules; this pins that the HTTP layer does
not leak more than they allow - particularly that a friend-request miss is
indistinguishable from a hit on an account that does not want to be found.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.social import services

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    return User.objects.create_user(username="alex", password=PASSWORD)


@pytest.fixture
def blake(db):
    return User.objects.create_user(username="blake", password=PASSWORD)


@pytest.fixture
def client_for():
    def _make(user):
        client = Client()
        client.force_login(user)
        return client

    return _make


def post(client, path, body=None):
    return client.post(path, data=json.dumps(body or {}), content_type="application/json")


def patch(client, path, body):
    return client.patch(path, data=json.dumps(body), content_type="application/json")


def test_the_whole_router_requires_authentication():
    assert Client().get("/api/v1/social/friends").status_code == 401


def test_a_request_to_a_real_user_and_to_nobody_are_indistinguishable(alex, blake, client_for):
    client = client_for(alex)
    blake.discoverable_by_username = False
    blake.save(update_fields=["discoverable_by_username"])

    real = post(client, "/api/v1/social/friend-requests", {"username": "blake"})
    fake = post(client, "/api/v1/social/friend-requests", {"username": "nobody-at-all"})

    assert real.status_code == fake.status_code == 202
    assert (
        real.json() == fake.json() == {"sent": False, "state": "no_action", "friendship_id": None}
    )


def test_a_request_accepted_over_http_puts_each_in_the_others_friends_list(alex, blake, client_for):
    alex_client, blake_client = client_for(alex), client_for(blake)

    sent = post(alex_client, "/api/v1/social/friend-requests", {"username": "blake"})
    assert sent.json()["sent"] is True

    pending = blake_client.get("/api/v1/social/friend-requests").json()
    assert [row["user"]["username"] for row in pending["incoming"]] == ["alex"]
    assert pending["outgoing"] == []
    # The same edge is outgoing for the sender - the split comes off
    # requested_by, not off the pair columns.
    assert [
        row["user"]["username"]
        for row in alex_client.get("/api/v1/social/friend-requests").json()["outgoing"]
    ] == ["blake"]

    friendship_id = pending["incoming"][0]["friendship_id"]
    assert (
        post(blake_client, f"/api/v1/social/friend-requests/{friendship_id}/accept").status_code
        == 200
    )

    assert [f["user"]["username"] for f in alex_client.get("/api/v1/social/friends").json()] == [
        "blake"
    ]
    assert [f["user"]["username"] for f in blake_client.get("/api/v1/social/friends").json()] == [
        "alex"
    ]


def test_pinning_a_friend_shows_only_on_the_pinners_list(alex, blake, client_for):
    services.send_request(alex, username="blake")
    services.accept_request(blake, services.get_friendship(alex, blake).pk)

    updated = patch(
        client_for(alex), f"/api/v1/social/friends/{blake.pk}/prefs", {"workout_partner": True}
    )

    assert updated.status_code == 200
    assert updated.json()["workout_partner"] is True
    friend_of_blake = client_for(blake).get("/api/v1/social/friends").json()[0]
    assert friend_of_blake["workout_partner"] is False


def test_the_friends_list_reports_the_friends_own_opt_out(alex, blake, client_for):
    services.send_request(alex, username="blake")
    services.accept_request(blake, services.get_friendship(alex, blake).pk)
    blake.allow_partner_logging = False
    blake.save(update_fields=["allow_partner_logging"])

    row = client_for(alex).get("/api/v1/social/friends").json()[0]

    # Shown so the picker can explain a name it renders but cannot tick.
    assert row["accepts_partner_logging"] is False


def test_settings_mint_a_friend_code_on_first_read(alex, client_for):
    body = client_for(alex).get("/api/v1/social/me").json()

    assert len(body["friend_code"]) == 10
    rotated = post(client_for(alex), "/api/v1/social/me/friend-code").json()
    assert rotated["friend_code"] != body["friend_code"]


def test_turning_off_username_discovery_takes_effect(alex, blake, client_for):
    patch(client_for(blake), "/api/v1/social/me", {"discoverable_by_username": False})

    ack = post(client_for(alex), "/api/v1/social/friend-requests", {"username": "blake"})

    assert ack.json()["sent"] is False


def test_answering_someone_elses_request_is_a_404(alex, blake, client_for):
    stranger = User.objects.create_user(username="casey", password=PASSWORD)
    edge = services.send_request(alex, username="blake")

    resp = post(client_for(stranger), f"/api/v1/social/friend-requests/{edge.pk}/accept")

    assert resp.status_code == 404
