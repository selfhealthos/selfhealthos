"""Photo upload for diet and doc entries.

A separate endpoint from `/sync/entries`: multipart bodies do not batch the
way JSON rows do, and it only ever fills in a row `/sync/entries` already
created. The failure this pins is a photo silently going nowhere - a row that
looks synced on the portal with no picture, and no signal to the phone about
why.
"""

from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from apps.health.models import DietEntry, Doc

User = get_user_model()
PASSWORD = "x" * 14
ENTRIES_ENDPOINT = "/api/v1/health/sync/entries"
PHOTO_ENDPOINT = "/api/v1/health/sync/photo"

#: A 1x1 GIF - the smallest thing Django will accept into an ImageField
#: without Pillow complaining about a truncated file.
TINY_IMAGE = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)


@pytest.fixture
def phone_user(db):
    return User.objects.create_user(username="phone", password=PASSWORD)


@pytest.fixture
def client(phone_user):
    c = Client()
    c.force_login(phone_user)
    return c


def sync_diet_entry(client, *, entry_id: str, name: str = "English breakfast") -> None:
    row = {
        "id": entry_id,
        "timestamp": 1_755_000_000_000,
        "updated_at": 1_755_000_000_000,
        "deleted": False,
        "name": name,
    }
    response = client.post(
        ENTRIES_ENDPOINT, data=json.dumps({"diet": [row]}), content_type="application/json"
    )
    assert response.status_code == 200
    assert row["id"] in response.json()["accepted"]


def upload_photo(client, *, kind: str, entry_id: str, filename: str = "meal.gif"):
    photo = SimpleUploadedFile(filename, TINY_IMAGE, content_type="image/gif")
    return client.post(PHOTO_ENDPOINT, data={"kind": kind, "id": entry_id, "file": photo})


class TestPhotoSync:
    def test_a_photo_for_a_synced_diet_entry_is_stored(self, client, phone_user, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            entry_id = str(uuid.uuid4())
            sync_diet_entry(client, entry_id=entry_id)

            response = upload_photo(client, kind="diet", entry_id=entry_id)
            body = response.json()

            assert response.status_code == 200
            assert body == {"stored": True, "reason": None}
            entry = DietEntry.objects.get(client_id=entry_id, created_by=phone_user)
            assert entry.photo
            assert entry.photo.read() == TINY_IMAGE

    def test_a_photo_for_a_row_that_has_not_synced_yet_is_named_not_stored(self, client, tmp_path):
        """The row must exist before its photo can attach to it. A phone that
        races the two - uploading the picture before the entry batch that
        creates the row - must be told to retry, not met with a 404 it cannot
        distinguish from "this will never work".
        """
        with override_settings(MEDIA_ROOT=tmp_path):
            response = upload_photo(client, kind="diet", entry_id=str(uuid.uuid4()))
            body = response.json()

            assert response.status_code == 200
            assert body == {"stored": False, "reason": "entry not synced yet"}

    def test_an_unknown_entry_type_is_rejected_by_name(self, client, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            response = upload_photo(client, kind="exercise", entry_id=str(uuid.uuid4()))
            body = response.json()

            assert response.status_code == 200
            assert body["stored"] is False
            assert "exercise" in body["reason"]

    def test_a_photo_cannot_attach_to_another_accounts_entry(self, client, tmp_path):
        """`client_id` is unique across the table, not per user (see
        `devicesync`) - a phone that names someone else's id must not be told
        whether that id exists at all, and must never see its file attached.
        """
        with override_settings(MEDIA_ROOT=tmp_path):
            owner = User.objects.create_user(username="owner", password=PASSWORD)
            entry_id = str(uuid.uuid4())
            DietEntry.objects.create(
                created_by=owner,
                client_id=entry_id,
                occurred_at="2026-08-25T08:00:00Z",
                local_date="2026-08-25",
                name="Someone else's breakfast",
            )

            response = upload_photo(client, kind="diet", entry_id=entry_id)
            body = response.json()

            assert response.status_code == 200
            assert body == {"stored": False, "reason": "entry not synced yet"}
            assert not DietEntry.objects.get(client_id=entry_id, created_by=owner).photo

    def test_a_photo_for_a_synced_doc_is_stored(self, client, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            entry_id = str(uuid.uuid4())
            row = {
                "id": entry_id,
                "timestamp": 1_755_000_000_000,
                "updated_at": 1_755_000_000_000,
                "deleted": False,
                "title": "Pathology result",
            }
            response = client.post(
                ENTRIES_ENDPOINT,
                data=json.dumps({"docs": [row]}),
                content_type="application/json",
            )
            assert entry_id in response.json()["accepted"]

            response = upload_photo(client, kind="docs", entry_id=entry_id)
            assert response.json() == {"stored": True, "reason": None}
            assert Doc.objects.get(client_id=entry_id).photo

    def test_anonymous_callers_are_refused(self, db, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            response = upload_photo(Client(), kind="diet", entry_id=str(uuid.uuid4()))
            assert response.status_code in (401, 403)
