"""Habit analytics: the completion calendar, streaks and rates.

Ported from the one-data dashboard's `get_habits_grid`, `get_habit_streaks`
and `get_habit_rates`, which read NDJSON through DuckDB. The logic is the same;
the source is Postgres and the shape is a dict the API can return directly.

The three share one pass over the completions rather than querying per habit.
The original ran a query for each of the three views and rebuilt the same
`{habit: {dates}}` map every time; with a dozen habits and a year of history
that is thirty-odd round trips to answer one page.

**A completion is an existence check, never a count.** There can be several
rows for one habit on one day - a second dose - and counting them would report
a 140% completion rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise

from .models import Habit, HabitCompletion


@dataclass(frozen=True)
class HabitRow:
    id: str
    name: str
    #: One bool per day in the window, oldest first, aligned to `dates`.
    days: list[bool]
    current_streak: int
    best_streak: int
    total: int
    rate_7: int
    rate_30: int

    @property
    def at_risk(self) -> bool:
        """Below half in the last month. What the dashboard flags with a ⚠."""
        return self.rate_30 < 50


def _ticked_dates(user) -> dict:
    """`{habit_id: {date, ...}}` for every completion, in one query.

    Whole history rather than the window, because the *current* streak can
    reach back before it - a 90-day streak is not visible in a 30-day grid, and
    reporting it as 30 would be wrong in the one direction that matters.
    """
    rows = HabitCompletion.objects.filter(created_by=user, deleted_at__isnull=True).values_list(
        "habit_id", "habit_name", "local_date"
    )
    by_habit: dict = {}
    by_name: dict = {}
    for habit_id, habit_name, day in rows:
        if habit_id is not None:
            by_habit.setdefault(habit_id, set()).add(day)
        # Completions that arrived before their habit definition have no link;
        # `habit_name` is denormalised for exactly this case.
        by_name.setdefault((habit_name or "").lower(), set()).add(day)
    return {"by_id": by_habit, "by_name": by_name}


def _streaks(ticked: set, today: date) -> tuple[int, int]:
    """Current streak ending today or yesterday, and the best ever."""
    if not ticked:
        return 0, 0

    # Counting back from today alone reports zero all morning, before the day's
    # habits are done. Yesterday is the honest anchor until today is ticked.
    anchor = today if today in ticked else today - timedelta(days=1)
    current = 0
    cursor = anchor
    while cursor in ticked:
        current += 1
        cursor -= timedelta(days=1)

    best = run = 1
    ordered = sorted(ticked)
    for previous, day in pairwise(ordered):
        if (day - previous).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1

    return current, max(best, current)


def overview(user, *, days: int = 30, today: date | None = None) -> dict:
    """The whole habits page in one call: grid, streaks and rates."""
    today = today or date.today()
    window = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    cutoff_7 = today - timedelta(days=6)

    habits = list(Habit.objects.filter(created_by=user, deleted_at__isnull=True, archived_at=None))
    lookup = _ticked_dates(user)

    rows: list[HabitRow] = []
    for habit in habits:
        # Prefer the foreign key; fall back to the name for completions that
        # arrived before their definition did.
        ticked = lookup["by_id"].get(habit.pk) or lookup["by_name"].get(habit.name.lower()) or set()
        current, best = _streaks(ticked, today)
        in_30 = {d for d in ticked if today - timedelta(days=29) <= d <= today}
        in_7 = {d for d in in_30 if d >= cutoff_7}

        rows.append(
            HabitRow(
                id=str(habit.pk),
                name=habit.name,
                days=[day in ticked for day in window],
                current_streak=current,
                best_streak=best,
                total=len(ticked),
                rate_7=round(len(in_7) / 7 * 100),
                rate_30=round(len(in_30) / 30 * 100),
            )
        )

    return {
        "days": days,
        "dates": window,
        "habits": [
            {
                "id": row.id,
                "name": row.name,
                "days": row.days,
                "current_streak": row.current_streak,
                "best_streak": row.best_streak,
                "total": row.total,
                "rate_7": row.rate_7,
                "rate_30": row.rate_30,
                "at_risk": row.at_risk,
            }
            for row in rows
        ],
    }
