"""Account settings that aren't authentication.

Thin, but it exists for the reason every other `services.py` here does: the
timezone is written from the browser today and will be written from a device
or an MCP tool tomorrow, and "is this a real zone" is a rule that must not be
re-decided per caller.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, available_timezones

from apps.core.exceptions import DomainError
from apps.core.services import record_event

from .models import User


class UnknownTimezone(DomainError):
    title = "Unknown timezone"


def _known() -> set[str]:
    """Every zone this machine's tz database can actually construct.

    Read fresh rather than cached at import: the set comes from the system
    tzdata, and a container that updates it mid-life should not need a restart
    to accept a zone that now exists.
    """
    return available_timezones()


def timezone_choices() -> list[str]:
    """The zones offered in the picker - region-qualified names only.

    `available_timezones()` also carries the legacy aliases (`US/Pacific`),
    the fixed-offset `Etc/GMT±N` family, and bare country names. All of them
    still *validate* - `set_timezone` accepts anything the tz database knows,
    so a client that sends one is not rejected - but none of them belong in a
    list a person scrolls. `Etc/GMT+10` is west of Greenwich, which is the
    opposite of what everybody reading it expects; offering it in a dropdown
    is offering a trap.
    """
    names = {
        name
        for name in _known()
        if "/" in name
        and not name.startswith(
            ("Etc/", "SystemV/", "US/", "Canada/", "Brazil/", "Mexico/", "Chile/")
        )
    }
    names.add("UTC")
    return sorted(names)


def set_timezone(user: User, name: str) -> User:
    """Point the subject's calendar at the place they actually live.

    This is the field every "what happened today" query is anchored to -
    `apps.health.timeutils.tz_for` reads it, and `local_date` is *stored* from
    it at write time. Leaving it at the `UTC` column default while living in
    +10 means an entry saved on Tuesday morning is filed under a Tuesday the
    server thinks is still the future, and every day-bounded read drops it.
    """
    name = (name or "").strip()
    if not name:
        raise UnknownTimezone("A timezone is required.")
    if name not in _known():
        raise UnknownTimezone(f"{name!r} is not a timezone this server recognises.")
    try:
        ZoneInfo(name)
    except Exception as exc:  # pragma: no cover - listed but unloadable
        raise UnknownTimezone(f"{name!r} could not be loaded as a timezone.") from exc

    if user.timezone == name:
        return user

    user.timezone = name
    user.save(update_fields=["timezone"])
    record_event(verb="user.timezone_updated", actor=user, target=user, summary=name)
    return user


def update_profile(user: User, *, timezone: str | None = None, fields=()) -> User:
    """Patch semantics: only the keys the request actually carried.

    Same shape as `apps.health.services.set_body_profile` and for the same
    reason - the profile page edits one field at a time, and a PUT here would
    let a form that only knows about the timezone blank out everything else.
    """
    if "timezone" in fields and timezone is not None:
        set_timezone(user, timezone)
    return user
