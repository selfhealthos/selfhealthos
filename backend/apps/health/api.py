"""REST surface for Health.

Thin by design: validate, call a service, shape the response. The MCP tools in
H4 call the same service functions, so the two cannot drift.

Every endpoint is scoped to `request.auth` - the logged-in user - rather than
taking a user parameter. Health data is read as one person's (roadmap decision
4); the shared-library pattern the rest of the portal uses does not fit a
weight chart.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from ninja import Router, Status

from apps.tokens.auth import require_scope

from . import connections, services
from .schemas import (
    HealthActivityDayOut,
    HealthActivityHistoryOut,
    HealthActivityOut,
    HealthAuthorizeOut,
    HealthBodyOut,
    HealthBristolDailyOut,
    HealthConnectionCredentialsIn,
    HealthConnectionOut,
    HealthDayOut,
    HealthDietLogOut,
    HealthDocOut,
    HealthEntrySyncIn,
    HealthExchangeIn,
    HealthGutOut,
    HealthGymSyncIn,
    HealthHabitHistoryOut,
    HealthHeartDayOut,
    HealthHeartHistoryOut,
    HealthHeatmapOut,
    HealthIntradayOut,
    HealthLabMarkerOut,
    HealthMetricOut,
    HealthNightOut,
    HealthNoteOut,
    HealthOfficeOut,
    HealthSleepHistoryOut,
    HealthSummaryOut,
    HealthSyncQueued,
    HealthSyncResultOut,
    HealthTrendOut,
    connection_to_schema,
)

router = Router(tags=["health"])

#: Default trend window. Long enough to show a direction, short enough to load
#: instantly on a phone.
DEFAULT_TREND_DAYS = 30


@router.get(
    "/summary",
    response=HealthSummaryOut,
    summary="What health data exists",
    operation_id="getHealthSummary",
)
def get_summary(request):
    return services.summary(request.auth)


@router.get(
    "/metrics",
    response=list[HealthMetricOut],
    summary="Metric vocabulary",
    operation_id="listHealthMetrics",
)
def list_metrics(request):
    return services.metric_catalogue()


@router.get(
    "/days/{on}",
    response=HealthDayOut,
    summary="One day in full",
    operation_id="getHealthDay",
)
def get_day(request, on: date):
    return services.day(request.auth, on)


@router.get(
    "/today",
    response=HealthDayOut,
    summary="The most recent day holding data",
    operation_id="getHealthToday",
)
def get_today(request):
    """Not literally today.

    Opening a dashboard at 6am, before the watch has synced and before anything
    has been logged, should not show an empty page - so this resolves to the
    latest day that actually has data.
    """
    on = services.latest_day_with_data(request.auth) or date.today()
    return services.day(request.auth, on)


@router.get(
    "/trend",
    response=HealthTrendOut,
    summary="A daily series with a moving average",
    operation_id="getHealthTrend",
)
def get_trend(
    request,
    metric: str,
    start: date | None = None,
    end: date | None = None,
    window: int = 7,
):
    end = end or services.latest_day_with_data(request.auth) or date.today()
    start = start or end - timedelta(days=DEFAULT_TREND_DAYS - 1)
    return services.trend(request.auth, metric, start, end, window=window)


@router.get(
    "/trends",
    response=list[HealthTrendOut],
    summary="Several daily series at once",
    operation_id="getHealthTrends",
)
def get_trends(
    request,
    metrics: str,
    start: date | None = None,
    end: date | None = None,
    window: int = 7,
):
    """`metrics` is a comma-separated list of keys.

    Exists so a page plotting nine series makes one request rather than nine.
    A key the vocabulary does not know is skipped, not rejected: the caller is
    a layout asking for what it would like to draw, and a metric this archive
    never held should leave a gap rather than a 400 where the page was.
    """
    end = end or services.latest_day_with_data(request.auth) or date.today()
    start = start or end - timedelta(days=DEFAULT_TREND_DAYS - 1)
    keys = [key.strip() for key in metrics.split(",") if key.strip()]
    return services.trends(request.auth, keys, start, end, window=window)


@router.get(
    "/heatmap",
    response=HealthHeatmapOut,
    summary="Every scored metric, one row per day",
    operation_id="getHealthHeatmap",
)
def get_heatmap(request, days: int = 30):
    """The grid: days down, metrics across, each cell scored against the
    thresholds in `scoring.py`."""
    return services.heatmap(request.auth, days=days)


@router.get(
    "/intraday",
    response=HealthIntradayOut,
    summary="One day of minute samples",
    operation_id="getHealthIntraday",
)
def get_intraday(request, metric: str, on: date):
    return services.intraday(request.auth, metric, on)


# --------------------------------------------------------------------------
# The deep-dive views
# --------------------------------------------------------------------------
#
# One endpoint per page rather than a generic entry-listing endpoint with a
# `kind` parameter. Each of these pages asks a different question - a habit
# grid is not a paginated list of completions, and the gut page's suspect table
# cannot be assembled client-side without shipping every food entry to the
# browser. A generic lister would have every page fetching three or four times
# and doing the joining itself.


@router.get(
    "/habits",
    response=HealthHabitHistoryOut,
    summary="Completion grid, streaks and recent rates",
    operation_id="getHealthHabits",
)
def get_habits(request, days: int = 30):
    return services.habit_history(request.auth, days=days)


@router.get(
    "/diet",
    response=HealthDietLogOut,
    summary="Food log, most-eaten items and caffeine timing",
    operation_id="getHealthDiet",
)
def get_diet(request, days: int = 30, q: str | None = None):
    return services.diet_log(request.auth, days=days, search=q)


@router.get(
    "/gut",
    response=HealthGutOut,
    summary="Bristol scores and what preceded the bad days",
    operation_id="getHealthGut",
)
def get_gut(request, days: int = 30):
    return services.gut_detail(request.auth, days=days)


@router.get(
    "/bristol",
    response=HealthBristolDailyOut,
    summary="Bristol score counts per day",
    operation_id="getHealthBristolDaily",
)
def get_bristol_daily(request, days: int = 90):
    """The cheap slice of `/gut`, for the stacked column on the trends page.

    Kept apart from `/gut` because that endpoint loads every food entry in the
    window to build its suspect table, which is three years of meals to draw
    one chart.
    """
    return services.bristol_daily(request.auth, days=days)


@router.get(
    "/body",
    response=HealthBodyOut,
    summary="Measurements and functional self-tests",
    operation_id="getHealthBody",
)
def get_body(request, days: int = 730):
    return services.body_history(request.auth, days=days)


@router.get(
    "/labs",
    response=list[HealthLabMarkerOut],
    summary="Blood markers, grouped by name",
    operation_id="listHealthLabs",
)
def get_labs(request):
    return services.lab_history(request.auth)


@router.get(
    "/notes",
    response=list[HealthNoteOut],
    summary="Diary entries, searchable",
    operation_id="listHealthNotes",
)
def get_notes(request, q: str | None = None, limit: int = 200):
    return services.note_list(request.auth, search=q, limit=limit)


@router.get(
    "/docs",
    response=list[HealthDocOut],
    summary="Photographed documents",
    operation_id="listHealthDocs",
)
def get_docs(request, limit: int = 200):
    return services.doc_list(request.auth, limit=limit)


@router.get(
    "/office",
    response=HealthOfficeOut,
    summary="Days worked in the office, by year",
    operation_id="getHealthOffice",
)
def get_office(request, year: int | None = None):
    return services.office_days(request.auth, year=year)


@router.get(
    "/sleep",
    response=HealthSleepHistoryOut,
    summary="Main sleep sessions with stage breakdowns",
    operation_id="getHealthSleep",
)
def get_sleep(request, days: int = 30):
    return services.sleep_history(request.auth, days=days)


@router.get(
    "/nights/{on}",
    response=HealthNightOut,
    summary="One night: hypnogram, minute series and the derived indices",
    operation_id="getHealthNight",
)
def get_night(request, on: date):
    """404 when nothing was recorded for that date.

    An empty hypnogram and a night that genuinely had none are different
    answers, and rendering them the same would let a sync failure pass for a
    night of no sleep.
    """
    return services.night(request.auth, on)


@router.get(
    "/heart",
    response=HealthHeartHistoryOut,
    summary="HRV and resting heart rate with baselines, and the scored table",
    operation_id="getHealthHeart",
)
def get_heart(request, days: int = 30):
    return services.heart_history(request.auth, days=days)


@router.get(
    "/heart/days/{on}",
    response=HealthHeartDayOut,
    summary="One day's heart rate trace, with the zones it moved through",
    operation_id="getHealthHeartDay",
)
def get_heart_day(request, on: date):
    return services.heart_day(request.auth, on)


@router.get(
    "/heart/latest",
    response=HealthHeartDayOut,
    summary="The most recent day holding minute-level heart rate",
    operation_id="getHealthHeartLatest",
)
def get_heart_latest(request):
    """Not literally today - see `services.latest_day_with_intraday`."""
    on = services.latest_day_with_intraday(request.auth) or date.today()
    return services.heart_day(request.auth, on)


@router.get(
    "/activity",
    response=HealthActivityHistoryOut,
    summary="Steps with their intensity, the overlays, and the scored table",
    operation_id="getHealthActivity",
)
def get_activity(request, days: int = 30, logged: bool = True):
    return services.activity_history(request.auth, days=days, logged=logged)


@router.get(
    "/activity/logged",
    response=HealthActivityOut,
    summary="Logged workouts by type and by week",
    operation_id="getHealthActivityLogged",
)
def get_activity_logged(request, days: int = 90):
    """The workout library on its own, for a caller that wants only that.

    Registered before `/activity/days/{on}` and `/activity/latest` purely as a
    matter of habit - the literal-before-parameterised rule that made
    `POST /connections/exchange` answer 405 applies to every sibling pair here.
    """
    return services.activity_detail(request.auth, days=days)


@router.get(
    "/activity/latest",
    response=HealthActivityDayOut,
    summary="The most recent day holding minute-level steps",
    operation_id="getHealthActivityLatest",
)
def get_activity_latest(request):
    """Not literally today - see `services.latest_day_with_intraday`."""
    on = services.latest_day_with_intraday(request.auth, metric="steps") or date.today()
    return services.activity_day(request.auth, on)


@router.get(
    "/activity/days/{on}",
    response=HealthActivityDayOut,
    summary="One day's cumulative step climb, by minute and by hour",
    operation_id="getHealthActivityDay",
)
def get_activity_day(request, on: date):
    return services.activity_day(request.auth, on)


# --------------------------------------------------------------------------
# Provider connections
# --------------------------------------------------------------------------
#
# The OAuth callback itself is *not* here. Fitbit sends the browser to
# /fitbit/callback on the Next.js frontend (see FITBIT_REDIRECT_URI); that
# route handler forwards the code and state to `exchange` below. Keeping the
# redirect on the frontend means the person lands on a page rather than on a
# JSON document, and the exchange stays a POST that mutates state.


@router.get(
    "/connections",
    response=list[HealthConnectionOut],
    summary="Wearable providers and their state",
    operation_id="listHealthConnections",
)
def list_connections(request):
    return [connection_to_schema(c) for c in connections.list_connections(request.auth)]


# Registered BEFORE /connections/{provider}, and it has to stay there.
#
# Django takes the first URL pattern that matches the path and never backtracks
# on a method mismatch, so `{provider}` - which happily matches the literal
# string "exchange" - would swallow this route and answer POST with
# "405, Allow: PUT, DELETE". That is a confusing failure: the endpoint is in
# the OpenAPI document, the path is right, and the method it rejects is the
# only one it is registered for. `tests/test_health_connections.py` pins it.
@router.post(
    "/connections/exchange",
    response=HealthConnectionOut,
    summary="Finish the OAuth flow",
    operation_id="exchangeHealthConnection",
)
def exchange_connection(request, payload: HealthExchangeIn):
    """Trade the authorization code for tokens.

    No provider in the path: `state` already records which flow this is, and
    trusting a path parameter over the state token would let a callback be
    redirected at a different provider's connection row.
    """
    connection = connections.exchange(request.auth, code=payload.code, state=payload.state)
    return connection_to_schema(connection)


@router.put(
    "/connections/{provider}",
    response=HealthConnectionOut,
    summary="Save a provider's client ID and secret",
    operation_id="saveHealthConnection",
)
def save_connection(request, provider: str, payload: HealthConnectionCredentialsIn):
    """Per-user credentials, not per-household.

    Fitbit grants intraday access automatically only to a Personal app, and
    only for the account that registered it - so everyone registers their own
    rather than the household sharing one and applying to Fitbit for access.
    """
    connection = connections.save_credentials(
        request.auth,
        provider,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
    )
    return connection_to_schema(connection)


@router.post(
    "/connections/{provider}/authorize",
    response=HealthAuthorizeOut,
    summary="Begin the OAuth flow",
    operation_id="authorizeHealthConnection",
)
def authorize_connection(request, provider: str):
    """Returns the provider URL for the browser to visit.

    Returned rather than redirected to, because the caller is `fetch` from a
    client component - a 302 here would be followed by the fetch and land the
    provider's HTML in a JSON parser.
    """
    url = connections.authorize(request.auth, provider, redirect_uri=settings.FITBIT_REDIRECT_URI)
    return HealthAuthorizeOut(authorize_url=url)


@router.delete(
    "/connections/{provider}",
    response=HealthConnectionOut,
    summary="Disconnect, keeping the saved credentials",
    operation_id="disconnectHealthConnection",
)
def disconnect_connection(request, provider: str):
    return connection_to_schema(connections.disconnect(request.auth, provider))


@router.post(
    "/connections/{provider}/sync",
    response={202: HealthSyncQueued},
    summary="Pull recent data from the provider",
    operation_id="syncHealthConnection",
)
def sync_connection(request, provider: str, days: int | None = None):
    """Queues the pull and returns immediately.

    A week of Fitbit is around 90 HTTP round trips; doing it inline would hold
    the browser's request open for minutes.
    """
    connections.queue_sync(request.auth, provider, days=days)
    return Status(
        202,
        HealthSyncQueued(
            provider=provider,
            queued=True,
            message="Syncing in the background. Reload in a minute to see it.",
        ),
    )


@router.post(
    "/sync/gym",
    response=HealthSyncResultOut,
    summary="Push gym entries from a device",
    operation_id="syncGymEntries",
)
def sync_gym(request, payload: HealthGymSyncIn):
    """Accepts a batch from the phone and reports what happened to each row.

    Returns 200 with per-row outcomes rather than 204, and that distinction is
    the whole contract: the device marks synced *only* the ids in `accepted`.
    An earlier version of this protocol answered 204 and the worker marked
    everything it had sent, so a single row the server refused was dropped from
    the phone as well - a silent, permanent loss with a 2xx in the log.

    Safe to replay. Identity is the phone's own UUID, so a request whose reply
    was lost to a dropped wifi connection can simply be sent again: the second
    attempt merges to the same rows and accepts the same ids.
    """
    require_scope(request, "health:write")
    result = services.ingest_gym(
        request.auth,
        exercises=[e.dict() for e in payload.exercises],
        sets=[s.dict() for s in payload.sets],
    )
    return HealthSyncResultOut(**result)


@router.post(
    "/sync/entries",
    response=HealthSyncResultOut,
    summary="Push hand-logged entries from a device",
    operation_id="syncHealthEntries",
)
def sync_entries(request, payload: HealthEntrySyncIn):
    """Every entry type except gym, in one batch.

    Same contract as `/sync/gym`, and for the same reason: the reply names the
    rows that were stored, and the phone marks synced only those. A batch is
    never accepted or rejected as a unit, because the phone's queue is the only
    copy of anything it has not yet sent - one unreadable date must not strand
    the forty good entries behind it.

    Safe to replay. Identity is the phone's own UUID, so a request whose reply
    was lost merges to the same rows on the second attempt.
    """
    require_scope(request, "health:write")
    result = services.ingest_entries(request.auth, payload.dict())
    return HealthSyncResultOut(**result)
