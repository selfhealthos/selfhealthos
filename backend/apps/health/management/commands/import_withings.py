"""Import Withings history from a data export, without connecting an account.

    python manage.py import_withings --user yourusername weight.csv
    python manage.py import_withings --user yourusername --dry-run export/*.csv

Takes either half of what Withings will give you:

  * **the CSV files** from the account data export (`weight.csv`, `bp.csv`) -
    Settings > Download my data in the Withings app, which arrives as a zip.
  * **a `getmeas` JSON dump**, i.e. a file holding the `measuregrps` array (or
    a whole response envelope containing one). This is what the probe script
    writes and what the live sync sees, so an import and a sync produce
    identical rows.

Idempotent: rows are keyed on the instant of the reading, so re-running an
import, or syncing a range a CSV already covered, adds nothing the second time.
That is deliberate - the usual way to use this is to import years of history
once and then let the ordinary sync keep up, and the two overlap at the join.

**Units come from the CSV header, never from an assumption.** Withings exports
in whatever the account is set to, so the same file is `Weight (kg)` for one
person and `Weight (lb)` for another. Reading a pounds column as kilograms
yields a number that is wrong by 2.2x and entirely plausible on a chart.

**CSV timestamps carry no timezone.** They are written in the account's local
time, so they are interpreted in the user's timezone - which is right for a
history recorded at home and wrong for a reading taken on holiday. The JSON
path does not have this problem: every measure group carries its own zone, and
that is what decides `local_date` there. Prefer the JSON if you have it and
your history spans a move.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.health import rollups, timeutils
from apps.health.providers import withings

#: Recognised CSV timestamp spellings, most specific first. Withings documents
#: `yyyy-mm-dd hh:mm:ss` for imports and writes that from the web export; the
#: am/pm form turns up in exports taken from the phone app.
DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %I:%M:%S %p",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)

#: Multiplier onto kilograms, by the unit named in the column header.
MASS_TO_KG = {
    "kg": 1.0,
    "kgs": 1.0,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "pounds": 0.45359237,
    "st": 6.35029318,
    "stone": 6.35029318,
}


class Command(BaseCommand):
    help = "Import Withings weight and blood pressure history from a CSV or getmeas JSON export."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="CSV and/or JSON files from the export.")
        parser.add_argument("--user", required=True, help="Username to file the readings under.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report, writing nothing. Run this first on a real export.",
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {options['user']!r}.") from exc

        tz = timeutils.tz_for(user)
        readings: list[withings.Reading] = []

        for raw_path in options["paths"]:
            path = Path(raw_path)
            if not path.exists():
                raise CommandError(f"{path} does not exist.")
            try:
                found = self._read(path, tz)
            except ValueError as exc:
                raise CommandError(f"{path}: {exc}") from exc
            self.stdout.write(f"{path.name}: {len(found)} readings")
            readings.extend(found)

        if not readings:
            self.stdout.write(self.style.WARNING("Nothing to import."))
            return

        # Oldest first, so a partial run leaves a contiguous history rather
        # than a scatter, and so the reported range reads naturally.
        readings.sort(key=lambda reading: reading.taken_at)
        first, last = readings[0].local_date, readings[-1].local_date
        self.stdout.write(f"\n{len(readings)} readings, {first} to {last}")

        if options["dry_run"]:
            self._preview(readings)
            self.stdout.write(self.style.WARNING("\nDry run - nothing written."))
            return

        report = withings.SyncReport()
        with transaction.atomic():
            touched = withings.write_readings(user, readings, report)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nWrote {report.weight_entries} weight entries, "
                f"{report.body_measurements} body measurements, "
                f"{report.bp_entries} blood pressure readings "
                f"({report.duplicates_skipped} already held)."
            )
        )

        if touched:
            # Outside the transaction above: rebuilding a decade of rollups is
            # the long part, and holding a write transaction open across it
            # would block every other writer for its duration.
            self.stdout.write(f"Rebuilding rollups for {min(touched)} to {max(touched)}...")
            rollups.rebuild(user, min(touched), max(touched))
            self.stdout.write(self.style.SUCCESS("Done."))

    # -- reading ---------------------------------------------------------

    def _read(self, path: Path, tz) -> list[withings.Reading]:
        if path.suffix.lower() == ".json":
            return self._read_json(path, tz)
        return self._read_csv(path, tz)

    def _read_json(self, path: Path, tz) -> list[withings.Reading]:
        """A `measuregrps` array, or anything that contains one."""
        payload = json.loads(path.read_text())

        if isinstance(payload, dict):
            # Accept a bare body, a full envelope, or the probe's raw dump.
            groups = payload.get("measuregrps") or (payload.get("body") or {}).get("measuregrps")
        else:
            groups = payload
        if not isinstance(groups, list):
            raise ValueError("expected a measuregrps array or an object containing one")

        readings = []
        for group in groups:
            reading = withings.reading_from_group(group, fallback_tz=tz)
            if reading is not None:
                readings.append(reading)
        return readings

    def _read_csv(self, path: Path, tz) -> list[withings.Reading]:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        if not rows:
            return []

        columns = _map_columns(rows[0].keys())
        if "date" not in columns:
            raise ValueError(f"no date column found (headers: {', '.join(rows[0].keys())})")
        if len(columns) == 1:
            raise ValueError("found a date column but no weight, fat or blood pressure column")

        readings = []
        for line, row in enumerate(rows, start=2):
            try:
                reading = _reading_from_row(row, columns, tz)
            except ValueError as exc:
                raise ValueError(f"line {line}: {exc}") from exc
            if reading is not None:
                readings.append(reading)
        return readings

    def _preview(self, readings: list[withings.Reading]) -> None:
        self.stdout.write("\nFirst three and last three:\n")
        sample = readings[:3] + readings[-3:] if len(readings) > 6 else readings
        for reading in sample:
            parts = []
            if reading.weight_kg is not None:
                parts.append(f"{reading.weight_kg:.3f} kg")
            if reading.fat_ratio_pct is not None:
                parts.append(f"{reading.fat_ratio_pct:.2f}% fat")
            if reading.fat_mass_kg is not None:
                parts.append(f"{reading.fat_mass_kg:.3f} kg fat mass")
            if reading.systolic is not None:
                parts.append(f"{reading.systolic}/{reading.diastolic} mmHg")
            self.stdout.write(f"  {reading.local_date}  {', '.join(parts)}")


# --------------------------------------------------------------------------
# CSV column handling
# --------------------------------------------------------------------------


def _map_columns(headers) -> dict[str, tuple[str, float]]:
    """Recognise Withings' export headers, and the unit each one carries.

    Returns `{field: (header, multiplier)}`. The multiplier converts the
    column's own unit to the one this app stores, which is the whole reason
    this is header-driven: `Weight (lb)` and `Weight (kg)` are the same export
    from two accounts.
    """
    found: dict[str, tuple[str, float]] = {}

    for header in headers:
        if header is None:
            continue
        name = header.strip().strip('"').lower()
        unit = _unit_in(name)

        if name.startswith("date"):
            found["date"] = (header, 1.0)
        elif name.startswith("weight"):
            found["weight_kg"] = (header, _mass_factor(header, unit))
        elif name.startswith("fat mass"):
            found["fat_mass_kg"] = (header, _mass_factor(header, unit))
        elif name.startswith("fat ratio") or name.startswith("fat percentage"):
            found["fat_ratio_pct"] = (header, 1.0)
        elif name.startswith("systolic"):
            found["systolic"] = (header, 1.0)
        elif name.startswith("diastolic"):
            found["diastolic"] = (header, 1.0)

    return found


def _unit_in(name: str) -> str:
    """The unit from a header like `weight (kg)`."""
    match = re.search(r"\(([^)]*)\)", name)
    return match.group(1).strip().lower() if match else ""


def _mass_factor(header: str, unit: str) -> float:
    if not unit:
        # Refused rather than assumed. A mass column with no unit in its header
        # is not a Withings export, and guessing kilograms here is exactly the
        # 2.2x error this function exists to prevent.
        raise ValueError(
            f"column {header!r} does not say what unit it is in - expected one like "
            f"'Weight (kg)' or 'Weight (lb)'"
        )
    try:
        return MASS_TO_KG[unit]
    except KeyError as exc:
        raise ValueError(
            f"column {header!r} is in {unit!r}, which this importer cannot convert"
        ) from exc


def _reading_from_row(row: dict, columns: dict, tz) -> withings.Reading | None:
    raw_date = (row.get(columns["date"][0]) or "").strip()
    if not raw_date:
        return None

    naive = _parse_datetime(raw_date)
    # The file's clock is the account's local time, so the calendar day is read
    # straight off it rather than round-tripped through UTC and back.
    local_date = naive.date()
    taken_at = timeutils.utc_from_local_parts(local_date, naive.time(), tz)

    values = {}
    for field in ("weight_kg", "fat_mass_kg", "fat_ratio_pct", "systolic", "diastolic"):
        if field not in columns:
            continue
        header, factor = columns[field]
        values[field] = _number(row.get(header), factor)

    reading = withings.Reading(
        taken_at=taken_at,
        local_date=local_date,
        weight_kg=values.get("weight_kg"),
        fat_ratio_pct=values.get("fat_ratio_pct"),
        fat_mass_kg=values.get("fat_mass_kg"),
        systolic=None if values.get("systolic") is None else round(values["systolic"]),
        diastolic=None if values.get("diastolic") is None else round(values["diastolic"]),
    )
    return None if reading.is_empty else reading


def _parse_datetime(value: str) -> datetime:
    cleaned = value.strip().strip('"')
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise ValueError(f"could not read {value!r} as a date")


def _number(raw, factor: float) -> float | None:
    """A blank cell is absent, not zero.

    Withings leaves the body-composition columns empty on a weigh-in that took
    no impedance reading. Reading those as 0.0 puts a zero-kilogram fat mass on
    the chart and drags every average through it.
    """
    if raw is None:
        return None
    text = str(raw).strip().strip('"')
    if not text:
        return None
    try:
        return float(text) * factor
    except ValueError as exc:
        raise ValueError(f"{text!r} is not a number") from exc
