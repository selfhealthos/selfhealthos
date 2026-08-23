"""The liveness probe.

It lives at /healthz rather than /health: it is infrastructure, and the Health
& Fitness app has the better claim on the readable path.
"""

import pytest
from django.test import Client


@pytest.mark.django_db
def test_healthz_reports_ok_when_dependencies_are_up():
    response = Client().get("/api/v1/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["components"]["database"]["ok"] is True
    assert payload["components"]["cache"]["ok"] is True


@pytest.mark.django_db
def test_openapi_schema_is_served():
    response = Client().get("/api/v1/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    # Paths in the document are absolute, including the /api/v1 mount point.
    assert "/api/v1/healthz" in schema["paths"]


@pytest.mark.django_db
def test_the_probe_did_not_take_the_health_apps_path():
    """A regression guard on the rename: /api/v1/health belongs to the app, and
    an unauthenticated caller must be refused rather than handed a probe."""
    response = Client().get("/api/v1/health/summary")

    assert response.status_code == 401
