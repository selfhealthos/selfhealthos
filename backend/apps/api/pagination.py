"""Keyset (cursor) pagination.

Offset pagination on a list that grows at the head silently duplicates and
skips rows as you page, and gets slower the deeper you go. Keyset on
`(created_at, id)` is stable under insertion and costs the same at any depth.
The id is the tiebreak, so two rows created in the same microsecond still have
a total order.

Exposed as a plain function rather than a ninja paginator class because the
routers build their response schemas explicitly - the same shapes go to Claude
over MCP, and auto-resolution would hide what crosses that boundary.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any

from django.db.models import Q, QuerySet

CURSOR_SEPARATOR = "|"
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def encode_cursor(created_at, pk) -> str:
    raw = f"{created_at.isoformat()}{CURSOR_SEPARATOR}{pk}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
        timestamp, pk = raw.split(CURSOR_SEPARATOR, 1)
        return timestamp, pk
    except (ValueError, binascii.Error, UnicodeDecodeError):
        # A malformed cursor is a client bug or a stale bookmark; start from
        # the beginning rather than returning a 500.
        return None


@dataclass(frozen=True)
class Page:
    items: list[Any]
    next_cursor: str | None
    has_more: bool


def paginate(queryset: QuerySet, *, cursor: str | None = None, limit: int = DEFAULT_LIMIT) -> Page:
    limit = max(1, min(limit, MAX_LIMIT))
    queryset = queryset.order_by("-created_at", "-id")

    if cursor:
        decoded = decode_cursor(cursor)
        if decoded:
            timestamp, pk = decoded
            queryset = queryset.filter(
                Q(created_at__lt=timestamp) | Q(created_at=timestamp, id__lt=pk)
            )

    # One extra row tells us whether another page exists, without a COUNT over
    # the whole table.
    rows = list(queryset[: limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].pk) if rows and has_more else None
    return Page(items=rows, next_cursor=next_cursor, has_more=has_more)
