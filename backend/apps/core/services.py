"""Shared service helpers.

Everything that mutates state goes through a service function, and anything
worth answering "who did that?" about writes an Event here.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import models

from .models import Event

logger = logging.getLogger(__name__)


def record_event(
    *,
    verb: str,
    actor=None,
    target: models.Model | None = None,
    target_type: str = "",
    target_id=None,
    **payload: Any,
) -> Event | None:
    """Append one row to the audit log.

    Never raises: losing an audit row is bad, but failing the user's actual
    request because the audit write failed is worse. Failures are logged.
    """
    if target is not None:
        target_type = target_type or f"{target._meta.app_label}.{target._meta.model_name}"
        target_id = target_id or target.pk

    actor_obj = actor if getattr(actor, "is_authenticated", False) else None

    try:
        return Event.objects.create(
            actor=actor_obj,
            verb=verb,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to record event %s", verb)
        return None
