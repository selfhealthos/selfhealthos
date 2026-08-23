"""MCP tools for Health.

Six tools shaped around questions a person asks, not one per REST endpoint.
"How did I sleep last week" should be one call, not a discovery call plus five
fetches - context spent on plumbing is context not spent on the answer.

Every tool answers for the token holder. Health data is one person's, so a tool
that cannot say whose data it is reading declines rather than guessing.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from mcp_server.auth import require_user
from mcp_server.django_setup import run_orm
from mcp_server.registry import scoped_tool

MAX_SEARCH_RESULTS = 50
#: A year of daily values is already a lot of tokens; beyond that the caller
#: wants a summary, not a series.
MAX_TREND_DAYS = 400


class MetricCoverage(BaseModel):
    metric: str
    label: str
    unit: str
    days: int
    first: str | None = None
    last: str | None = None


class HealthOverview(BaseModel):
    subject: str
    first_date: str | None = None
    last_date: str | None = None
    days_covered: int
    entry_counts: dict[str, int]
    metrics: list[MetricCoverage]
    hint: str


class DayEntry(BaseModel):
    at: str | None = None
    summary: str


class HealthDay(BaseModel):
    date: str
    timezone: str
    metrics: dict[str, float]
    sleep: dict | None = None
    food: list[DayEntry] = []
    exercise: list[DayEntry] = []
    gym: list[DayEntry] = []
    gut: list[DayEntry] = []
    notes: list[DayEntry] = []
    habits_done: list[str] = []
    habits_missed: list[str] = []
    office_day: bool = False


class TrendPoint(BaseModel):
    date: str
    value: float
    average: float | None = None


class HealthTrend(BaseModel):
    metric: str
    label: str
    unit: str
    start: str
    end: str
    days_with_data: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    first_half_mean: float | None = None
    second_half_mean: float | None = None
    direction: str = Field(description="rising, falling or flat, comparing the two halves")
    points: list[TrendPoint]


class Correlation(BaseModel):
    metric_a: str
    metric_b: str
    paired_days: int
    coefficient: float | None = None
    strength: str
    caution: str
    pairs: list[dict]


class SearchHit(BaseModel):
    kind: str
    date: str
    text: str


class SearchResult(BaseModel):
    query: str
    matched: int
    returned: int
    truncated: bool
    hits: list[SearchHit]


class LogResult(BaseModel):
    created: bool
    kind: str
    id: str
    date: str
    summary: str


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _describe_direction(first: float | None, second: float | None) -> str:
    if first is None or second is None:
        return "unknown"
    if first == 0:
        return "rising" if second > 0 else "flat"
    change = (second - first) / abs(first)
    if change > 0.05:
        return "rising"
    if change < -0.05:
        return "falling"
    return "flat"


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 3)


def _strength(r: float | None) -> str:
    if r is None:
        return "not enough overlapping days to say"
    a = abs(r)
    if a >= 0.7:
        return "strong"
    if a >= 0.4:
        return "moderate"
    if a >= 0.2:
        return "weak"
    return "negligible"


def register(mcp) -> None:
    @scoped_tool(mcp, scope="health:read")
    async def health_describe() -> HealthOverview:
        """What health data exists, over what period, and how complete it is.

        Call this before any other health tool. It returns no records - just
        which metrics are populated and their date ranges - so you can ask for
        a metric that exists rather than discovering emptiness one call at a
        time.
        """

        def _query() -> HealthOverview:
            from apps.health import metrics as metric_defs
            from apps.health import services

            user = require_user()
            data = services.summary(user)
            coverage = []
            for key, info in data["metrics"].items():
                definition = metric_defs.DAILY_BY_KEY.get(key)
                coverage.append(
                    MetricCoverage(
                        metric=key,
                        label=definition.label if definition else key,
                        unit=definition.unit if definition else "",
                        days=info["days"],
                        first=_iso(info["first"]),
                        last=_iso(info["last"]),
                    )
                )
            coverage.sort(key=lambda m: (-m.days, m.metric))
            return HealthOverview(
                subject=user.username,
                first_date=_iso(data["first_date"]),
                last_date=_iso(data["last_date"]),
                days_covered=data["days_covered"],
                entry_counts=data["entries"],
                metrics=coverage,
                hint=(
                    "health_day for one date in full, health_trend for a metric over "
                    "time, health_correlate to compare two metrics, health_search for "
                    "free text in notes and the food diary. Dates are the subject's "
                    "local calendar days."
                ),
            )

        return await run_orm(_query)

    @scoped_tool(mcp, scope="health:read")
    async def health_day(on: str | None = None) -> HealthDay:
        """Everything recorded for one day: sleep, activity, heart, food,
        training, gut, habits and notes.

        `on` is an ISO date. Omit it for the most recent day holding data,
        which is usually more useful than today - the watch syncs in batches,
        so today is often empty until the evening.
        """

        def _query() -> HealthDay:
            from apps.health import services

            user = require_user()
            day = date.fromisoformat(on) if on else services.latest_day_with_data(user)
            if day is None:
                raise ValueError("There is no health data for this account yet.")

            view = services.day(user, day)
            return HealthDay(
                date=view.date.isoformat(),
                timezone=view.timezone,
                metrics=view.metrics,
                sleep=view.sleep,
                food=[DayEntry(at=_iso(e["at"]), summary=e["name"]) for e in view.diet],
                exercise=[
                    DayEntry(
                        at=_iso(e["at"]),
                        summary=f"{e['name']} ({round(e['duration_s'] / 60, 1)} min)",
                    )
                    for e in view.exercise
                ],
                gym=[
                    DayEntry(
                        summary=f"{e['exercise']} {e['weight_kg']}kg x {e['reps']} "
                        f"= {e['volume_kg']}kg"
                    )
                    for e in view.gym_sets
                ],
                gut=[
                    DayEntry(at=_iso(e["at"]), summary=f"Bristol {e['bristol']}") for e in view.bm
                ],
                notes=[
                    DayEntry(at=_iso(e["at"]), summary=e["title"] or e["content"][:200])
                    for e in view.notes
                ],
                habits_done=[h["name"] for h in view.habits if h["completed"]],
                habits_missed=[h["name"] for h in view.habits if not h["completed"]],
                office_day=view.office_day,
            )

        return await run_orm(_query)

    @scoped_tool(mcp, scope="health:read")
    async def health_trend(metric: str, days: int = 30, end: str | None = None) -> HealthTrend:
        """One metric over a date range, with a moving average and direction.

        Compares the mean of the first half of the window against the second,
        so "is my resting heart rate improving" is answered rather than left
        for you to eyeball out of a list of numbers.
        """

        def _query() -> HealthTrend:
            from apps.health import services

            user = require_user()
            last = date.fromisoformat(end) if end else services.latest_day_with_data(user)
            if last is None:
                raise ValueError("There is no health data for this account yet.")
            span = max(1, min(days, MAX_TREND_DAYS))
            first = last - timedelta(days=span - 1)

            data = services.trend(user, metric, first, last, window=7)
            values = [p["value"] for p in data["points"]]
            half = len(values) // 2
            first_half = sum(values[:half]) / half if half else None
            second_half = sum(values[half:]) / (len(values) - half) if half else None

            return HealthTrend(
                metric=data["metric"],
                label=data["label"],
                unit=data["unit"],
                start=data["start"].isoformat(),
                end=data["end"].isoformat(),
                days_with_data=data["count"],
                minimum=data["minimum"],
                maximum=data["maximum"],
                mean=round(data["mean"], 2) if data["mean"] is not None else None,
                first_half_mean=round(first_half, 2) if first_half is not None else None,
                second_half_mean=round(second_half, 2) if second_half is not None else None,
                direction=_describe_direction(first_half, second_half),
                points=[
                    TrendPoint(
                        date=p["date"].isoformat(),
                        value=p["value"],
                        average=round(p["average"], 2) if p["average"] is not None else None,
                    )
                    for p in data["points"]
                ],
            )

        return await run_orm(_query)

    @scoped_tool(mcp, scope="health:read")
    async def health_correlate(
        metric_a: str, metric_b: str, days: int = 90, offset_days: int = 0
    ) -> Correlation:
        """Compare two metrics over the days both were recorded.

        `offset_days` shifts the second metric forward, which is how you ask
        whether yesterday's training affected today's recovery rather than
        whether they merely happened together.
        """

        def _query() -> Correlation:
            from apps.health import services
            from apps.health.models import DailyMetric

            user = require_user()
            last = services.latest_day_with_data(user)
            if last is None:
                raise ValueError("There is no health data for this account yet.")
            span = max(7, min(days, MAX_TREND_DAYS))
            first = last - timedelta(days=span - 1)

            services.resolve_metric(metric_a)
            services.resolve_metric(metric_b)

            def series(metric: str) -> dict[date, float]:
                return dict(
                    DailyMetric.objects.filter(user=user)
                    .series(metric, first - timedelta(days=abs(offset_days)), last)
                    .values_list("local_date", "value")
                )

            a_values, b_values = series(metric_a), series(metric_b)
            pairs = []
            for day, a in sorted(a_values.items()):
                b = b_values.get(day + timedelta(days=offset_days))
                if b is not None and first <= day <= last:
                    pairs.append({"date": day.isoformat(), metric_a: a, metric_b: b})

            xs = [p[metric_a] for p in pairs]
            ys = [p[metric_b] for p in pairs]
            r = _pearson(xs, ys)

            return Correlation(
                metric_a=metric_a,
                metric_b=metric_b,
                paired_days=len(pairs),
                coefficient=r,
                strength=_strength(r),
                caution=(
                    "This is association over a small personal sample, not cause. "
                    "Say so when reporting it."
                ),
                pairs=pairs[:MAX_TREND_DAYS],
            )

        return await run_orm(_query)

    @scoped_tool(mcp, scope="health:read")
    async def health_search(query: str, limit: int = 25) -> SearchResult:
        """Free-text search across diary notes and the food diary.

        For "when did I last eat X" or "what did I write about my knee".
        """

        def _query() -> SearchResult:
            from apps.health.models import DietEntry, Note

            user = require_user()
            text = (query or "").strip()
            if not text:
                raise ValueError("Provide something to search for.")
            capped = max(1, min(limit, MAX_SEARCH_RESULTS))

            notes = Note.objects.filter(created_by=user, deleted_at__isnull=True).filter(
                title__icontains=text
            ) | Note.objects.filter(created_by=user, deleted_at__isnull=True).filter(
                content__icontains=text
            )
            foods = DietEntry.objects.filter(
                created_by=user, deleted_at__isnull=True, name__icontains=text
            )

            hits = [
                SearchHit(
                    kind="note",
                    date=n.local_date.isoformat(),
                    text=(n.title or n.content)[:300],
                )
                for n in notes.order_by("-local_date")[: capped + 1]
            ] + [
                SearchHit(kind="food", date=f.local_date.isoformat(), text=f.name)
                for f in foods.order_by("-local_date")[: capped + 1]
            ]
            hits.sort(key=lambda h: h.date, reverse=True)
            matched = notes.count() + foods.count()

            return SearchResult(
                query=text,
                matched=matched,
                returned=min(len(hits), capped),
                truncated=matched > capped,
                hits=hits[:capped],
            )

        return await run_orm(_query)

    @scoped_tool(mcp, scope="health:write")
    async def health_log(
        kind: str,
        value: float | None = None,
        text: str = "",
        systolic: int | None = None,
        diastolic: int | None = None,
        on: str | None = None,
    ) -> LogResult:
        """Record a health entry.

        `kind` is one of: weight (value in kg), bp (systolic and diastolic),
        bm (value 1-7 on the Bristol scale), food (text), note (text).
        `on` is an ISO date, defaulting to today in the subject's timezone.
        """

        def _mutate() -> LogResult:
            from apps.health import services

            user = require_user()
            entry, summary = services.log_entry(
                user,
                kind=kind,
                value=value,
                text=text,
                systolic=systolic,
                diastolic=diastolic,
                on=date.fromisoformat(on) if on else None,
            )
            return LogResult(
                created=True,
                kind=kind,
                id=str(entry.pk),
                date=entry.local_date.isoformat(),
                summary=summary,
            )

        return await run_orm(_mutate)
