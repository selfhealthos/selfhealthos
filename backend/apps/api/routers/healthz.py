"""Liveness/readiness probe.

Checks its dependencies rather than just returning 200, so the Compose
healthcheck fails when Postgres or Redis is unreachable instead of reporting a
container that cannot actually serve a request.
"""

import logging

from django.core.cache import cache
from django.db import connection
from ninja import Router, Schema, Status

from selfhealthos import __version__

logger = logging.getLogger(__name__)

router = Router(tags=["system"])


class ComponentStatus(Schema):
    ok: bool
    detail: str | None = None


class HealthOut(Schema):
    status: str
    version: str
    components: dict[str, ComponentStatus]


def _check_database() -> ComponentStatus:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        logger.warning("health: database check failed: %s", exc)
        return ComponentStatus(ok=False, detail=type(exc).__name__)
    return ComponentStatus(ok=True)


def _check_cache() -> ComponentStatus:
    try:
        cache.set("health:ping", "pong", timeout=10)
        if cache.get("health:ping") != "pong":
            return ComponentStatus(ok=False, detail="round-trip mismatch")
    except Exception as exc:
        logger.warning("health: cache check failed: %s", exc)
        return ComponentStatus(ok=False, detail=type(exc).__name__)
    return ComponentStatus(ok=True)


@router.get(
    "",
    response={200: HealthOut, 503: HealthOut},
    auth=None,
    summary="Service health",
    operation_id="getHealth",
)
def health(request):
    components = {
        "database": _check_database(),
        "cache": _check_cache(),
    }
    healthy = all(component.ok for component in components.values())
    payload = HealthOut(
        status="ok" if healthy else "degraded",
        version=__version__,
        components=components,
    )
    return Status(200 if healthy else 503, payload)
