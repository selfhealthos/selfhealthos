"""The two timestamp conventions in the one-data archive.

App records are true UTC epochs; Fitbit records are Melbourne wall-clock encoded
as though they were UTC. Reading both the same way puts every Fitbit record ten
hours out, so these tests pin the distinction with values taken from the real
archive.
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from apps.health import timeutils

MELBOURNE = ZoneInfo("Australia/Melbourne")


def test_app_timestamp_is_a_true_utc_instant():
    """A diet entry from the archive: 1780509802605.

    The archive files this record under `data/2026/06/04/`, a day later than
    its UTC date - which is the check that the localisation is right way round,
    and what reading the epoch as a naive UTC date would get wrong.
    """
    moment = timeutils.utc_from_epoch_ms(1780509802605)

    assert moment == datetime(2026, 6, 3, 18, 3, 22, 605000, tzinfo=UTC)
    assert moment.astimezone(MELBOURNE).date() == date(2026, 6, 4)


def test_fitbit_timestamp_is_local_wall_clock_wearing_utc():
    """An intraday reading labelled 2026-06-07 00:00:00 stores as
    1780790400000, but the real instant is ten hours earlier."""
    naive_read = timeutils.utc_from_epoch_ms(1780790400000)
    corrected = timeutils.utc_from_local_epoch_ms(1780790400000, MELBOURNE)

    assert naive_read == datetime(2026, 6, 7, 0, 0, tzinfo=UTC)
    assert corrected == datetime(2026, 6, 6, 14, 0, tzinfo=UTC)
    assert (naive_read - corrected).total_seconds() == 36000  # AEST, +10

    # And the point of the exercise: the local calendar day is preserved.
    assert corrected.astimezone(MELBOURNE).date() == date(2026, 6, 7)
    assert corrected.astimezone(MELBOURNE).hour == 0


def test_daylight_saving_is_not_a_fixed_offset():
    """The archive spans April 2026, so a hardcoded +10 would be wrong for
    every record before the change."""
    january = timeutils.utc_from_local_parts(date(2026, 1, 15), time(0, 0), MELBOURNE)
    june = timeutils.utc_from_local_parts(date(2026, 6, 15), time(0, 0), MELBOURNE)

    assert january == datetime(2026, 1, 14, 13, 0, tzinfo=UTC)  # AEDT, +11
    assert june == datetime(2026, 6, 14, 14, 0, tzinfo=UTC)  # AEST, +10


def test_local_date_of_an_early_morning_instant():
    """00:30 Melbourne is the previous afternoon in UTC; the day it belongs to
    is the local one, which is why `local_date` is stored."""
    moment = timeutils.utc_from_local_parts(date(2026, 6, 7), time(0, 30), MELBOURNE)

    assert moment.date() == date(2026, 6, 6)
    assert timeutils.local_date_of(moment, MELBOURNE) == date(2026, 6, 7)


def test_missing_and_zero_timestamps_are_none():
    assert timeutils.utc_from_epoch_ms(None) is None
    assert timeutils.utc_from_epoch_ms(0) is None
    assert timeutils.utc_from_local_epoch_ms(0, MELBOURNE) is None


def test_floor_to_minute_drops_seconds():
    moment = datetime(2026, 6, 7, 8, 42, 37, 500000, tzinfo=UTC)

    assert timeutils.floor_to_minute(moment) == datetime(2026, 6, 7, 8, 42, tzinfo=UTC)
