"""Epoch-millisecond conversion, and the one trap in the archive.

The `one-data` files carry two incompatible kinds of `timestamp`, and nothing in
the files says which is which:

**App data is a true UTC instant.** Android's `System.currentTimeMillis()` is
milliseconds since the epoch, UTC, unambiguously.

**Fitbit data is local wall-clock encoded as though it were UTC.**
`fitbit_sync.py` builds every timestamp with `calendar.timegm()` applied to a
*naive local* datetime::

    def _day_timestamp(d: date) -> int:
        '''Midnight of the date as epoch ms (local time).'''
        midnight = datetime(d.year, d.month, d.day, 0, 0, 0)
        return int(calendar.timegm(midnight.timetuple()) * 1000)

`timegm` interprets its argument as UTC, so midnight in Melbourne is written as
midnight UTC. Verified against the archive: an intraday reading labelled
``2026-06-07 00:00:00`` is stored as ``1780790400000``, while the true instant is
``1780754400000`` - exactly the ten-hour AEST offset.

Read both the same way and every Fitbit record lands ten hours off: sleep
sessions fall on the wrong side of midnight, and a workout logged on the phone
sits ten hours away from the heart rate that recorded it. The archive spans the
April daylight-saving change, so a fixed offset is not a fix either - the
conversion has to go through a real timezone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("Australia/Melbourne")


def tz_for(user) -> ZoneInfo:
    """The subject's timezone. `User.timezone` already defaults to Melbourne."""
    name = getattr(user, "timezone", None)
    if not name:
        return DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        return DEFAULT_TZ


def utc_from_epoch_ms(ms: int | float | None) -> datetime | None:
    """A true UTC epoch in milliseconds. Use for anything the phone wrote."""
    if ms in (None, 0):
        return None
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)


def utc_from_local_epoch_ms(ms: int | float | None, tz: ZoneInfo) -> datetime | None:
    """A local wall-clock time that was encoded as if it were UTC.

    Use for anything `fitbit_sync.py` wrote. Reads the calendar fields back out
    in UTC, then reattaches them to the real timezone - which is where DST is
    handled, because `ZoneInfo` picks the right offset for that date.
    """
    if ms in (None, 0):
        return None
    naive = datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC).replace(tzinfo=None)
    return naive.replace(tzinfo=tz).astimezone(UTC)


def utc_from_local_parts(day: date, clock: time, tz: ZoneInfo) -> datetime:
    """Build a UTC instant from a local date and time.

    Preferred over `utc_from_local_epoch_ms` wherever the file carries `date`
    and `time` fields, because it depends on what the record says rather than on
    reverse-engineering how the timestamp was built.
    """
    return datetime.combine(day, clock).replace(tzinfo=tz).astimezone(UTC)


def local_date_of(moment: datetime | None, tz: ZoneInfo) -> date | None:
    if moment is None:
        return None
    return moment.astimezone(tz).date()


def parse_hms(value: str) -> time:
    """Fitbit intraday `time` fields are "HH:MM:SS"."""
    hh, mm, ss = (int(part) for part in value.split(":"))
    return time(hh, mm, ss)


def floor_to_minute(moment: datetime) -> datetime:
    """1-minute buckets are the storage resolution (roadmap decision 1)."""
    return moment.replace(second=0, microsecond=0)


def parse_date(value) -> date | None:
    """A plain "YYYY-MM-DD", or None if it is anything else.

    Deliberately strict. A provider that starts sending a different shape
    should surface as a missing day rather than as a date guessed from a
    prefix and filed under the wrong one.
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def parse_local_iso(value: str, tz: ZoneInfo) -> datetime | None:
    """An ISO timestamp written in local wall clock, converted to UTC.

    Fitbit writes intraday timestamps with no offset - "2026-06-04T23:12:00" is
    11:12pm where the watch was, not 11:12pm UTC. Reading them as UTC files a
    late-evening reading under the following day, ten hours out in Melbourne.
    A value that *does* carry an offset is trusted as-is.
    """
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is not None:
        return moment.astimezone(UTC)
    return moment.replace(tzinfo=tz).astimezone(UTC)
