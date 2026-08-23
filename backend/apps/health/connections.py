"""Connecting a wearable, and pulling from it.

Provider-agnostic on purpose: everything here works in terms of a `Connection`
and a provider module resolved from `PROVIDERS`, so adding Withings or Strava
is a new file in `providers/` and one line in that table.

The OAuth handshake is three calls that have to agree with each other:

    authorize()  -> stashes state+verifier, returns the URL for the browser
    (the person approves at fitbit.com; the browser comes back with ?code)
    exchange()   -> consumes state, trades the code for tokens
    sync()       -> queues the pull

`state` is what makes the callback safe. It is single-use, bound to the user
who started the flow, and held in the cache with a short TTL - so a callback
replayed later, or arriving at a different person's session, is refused rather
than silently attaching someone else's Fitbit account to this profile.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.core.exceptions import DomainError, NotFound
from apps.core.services import record_event

from .models import Connection
from .providers import fitbit

logger = logging.getLogger(__name__)

PROVIDERS = {Connection.Provider.FITBIT: fitbit}

#: How long the person has to finish approving at the provider. Long enough to
#: find a password, short enough that an abandoned flow cannot be resumed by
#: whoever next uses the browser.
STATE_TTL_S = 600

#: Days pulled by a plain "Sync now" when the connection has never synced.
DEFAULT_BACKFILL_DAYS = 7

#: Ceiling on one job. Fitbit allows 150 requests an hour and a day costs about
#: a dozen, so a longer range would simply hit the limit and stop - better to
#: say so up front than to look like it failed.
MAX_SYNC_DAYS = 30

#: Re-pull recent days even if they were synced before. The watch backfills:
#: sleep stages and resting heart rate for last night can land hours later, so
#: a strictly incremental sync captures the gaps and never the corrections.
OVERLAP_DAYS = 2


class UnknownProvider(DomainError):
    title = "Unknown provider"


def _module(provider: str):
    module = PROVIDERS.get(provider)
    if module is None:
        raise UnknownProvider(f"{provider!r} is not a provider this portal supports.")
    return module


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def list_connections(user) -> list[Connection]:
    """Every supported provider, connected or not.

    Returns a row per provider rather than only the saved ones, so the settings
    page can render "Fitbit — not connected" without knowing the vocabulary.
    """
    existing = {c.provider: c for c in Connection.objects.filter(user=user)}
    return [
        existing.get(provider) or Connection(user=user, provider=provider) for provider in PROVIDERS
    ]


def get_connection(user, provider: str) -> Connection:
    _module(provider)
    connection = Connection.objects.filter(user=user, provider=provider).first()
    if connection is None:
        raise NotFound("That provider has not been set up yet.")
    return connection


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------


def save_credentials(user, provider: str, *, client_id: str, client_secret: str) -> Connection:
    """Store the app registration for one person.

    A blank secret leaves the stored one alone, so the settings form can render
    without ever sending the secret to the browser and be re-saved to change
    only the client id.
    """
    _module(provider)
    client_id = (client_id or "").strip()
    if not client_id:
        raise DomainError("A client ID is required.")

    connection, _ = Connection.objects.get_or_create(user=user, provider=provider)

    changed_client = connection.client_id != client_id
    connection.client_id = client_id
    fields = ["client_id", "updated_at"]

    if client_secret and client_secret.strip():
        connection.client_secret = client_secret.strip()
        fields.append("client_secret_enc")
    elif not connection.client_secret_enc:
        raise DomainError("A client secret is required the first time.")

    # Changing the registration invalidates any grant issued under the old one.
    if changed_client and connection.is_connected:
        connection.access_token = ""
        connection.refresh_token = ""
        connection.status = Connection.Status.CONFIGURED
        fields += ["access_token_enc", "refresh_token_enc", "status"]

    connection.save(update_fields=fields)
    record_event(verb="health.connection.configured", actor=user, target=connection)
    return connection


def disconnect(user, provider: str) -> Connection:
    """Drop the grant, keep the registration.

    Deliberately not a delete: the client id and secret are the tedious part to
    set up, and "disconnect" almost always means "reconnect in a minute".
    """
    module = _module(provider)
    connection = get_connection(user, provider)

    module.revoke(connection)
    connection.access_token = ""
    connection.refresh_token = ""
    connection.token_expires_at = None
    connection.scopes = []
    connection.status = Connection.Status.CONFIGURED
    connection.connected_at = None
    connection.save(
        update_fields=[
            "access_token_enc",
            "refresh_token_enc",
            "token_expires_at",
            "scopes",
            "status",
            "connected_at",
            "updated_at",
        ]
    )
    record_event(verb="health.connection.disconnected", actor=user, target=connection)
    return connection


# --------------------------------------------------------------------------
# The OAuth handshake
# --------------------------------------------------------------------------


def _state_key(state: str) -> str:
    return f"health:oauth:{state}"


def authorize(user, provider: str, *, redirect_uri: str) -> str:
    """Begin the flow. Returns the URL to send the browser to."""
    module = _module(provider)
    connection = get_connection(user, provider)

    request = module.start_authorization(connection, redirect_uri)
    cache.set(
        _state_key(request.state),
        {
            "user_id": str(user.pk),
            "provider": provider,
            "verifier": request.verifier,
            "redirect_uri": redirect_uri,
        },
        STATE_TTL_S,
    )
    return request.url


def exchange(user, *, code: str, state: str) -> Connection:
    """Finish the flow.

    The state token decides everything: which provider, which PKCE verifier,
    and whose account this grant may attach to. An unknown or expired state is
    refused outright rather than being treated as a bare code to redeem.
    """
    stashed = cache.get(_state_key(state))
    if not stashed:
        raise DomainError(
            "That sign-in link has expired or was already used. Start the connection again."
        )
    # Single use. Deleted before anything else can fail, so a replay of the
    # same callback cannot get a second attempt.
    cache.delete(_state_key(state))

    if stashed.get("user_id") != str(user.pk):
        # The flow was started by someone else in this browser. Attaching the
        # grant here would file their Fitbit history under this profile.
        logger.warning("oauth state for user %s presented by %s", stashed.get("user_id"), user.pk)
        raise DomainError("That sign-in was started by a different account.")

    provider = stashed["provider"]
    module = _module(provider)
    connection = get_connection(user, provider)

    module.exchange_code(
        connection,
        code=code,
        verifier=stashed["verifier"],
        redirect_uri=stashed["redirect_uri"],
    )
    record_event(verb="health.connection.connected", actor=user, target=connection)
    return connection


# --------------------------------------------------------------------------
# Syncing
# --------------------------------------------------------------------------


def queue_sync(user, provider: str, *, days: int | None = None) -> Connection:
    """Hand the pull to the worker and return immediately.

    Not run inline: a week of Fitbit data is ~90 HTTP round trips, which is
    minutes of a request the browser would be holding open.
    """
    connection = get_connection(user, provider)
    if not connection.is_connected:
        raise DomainError("Connect this provider before syncing.")

    from .tasks import sync_connection

    sync_connection.delay(str(connection.pk), days=days)
    return connection


def run_sync(connection_pk: str, *, days: int | None = None) -> dict:
    """Do the pull. Worker only. Records the outcome on the connection row."""
    connection = Connection.objects.select_related("user").filter(pk=connection_pk).first()
    if connection is None:  # pragma: no cover - deleted mid-flight
        logger.warning("connection %s vanished before its sync ran", connection_pk)
        return {}

    module = _module(connection.provider)
    start, end = sync_window(connection, days)

    try:
        report = module.sync(connection, start=start, end=end)
    except DomainError as exc:
        Connection.objects.filter(pk=connection.pk).update(
            last_sync_at=timezone.now(), last_sync_error=str(exc.detail)[:1000]
        )
        logger.warning("sync failed for connection %s: %s", connection.pk, exc.detail)
        return {"error": str(exc.detail)}

    _finish(connection, report)
    return report.as_dict()


def sync_window(connection: Connection, days: int | None) -> tuple[date, date]:
    """Which dates to pull.

    An explicit `days` wins. Otherwise resume from the last successful day,
    minus an overlap - the watch backfills last night's sleep stages and
    resting heart rate hours after the fact, so a sync that only ever moves
    forward collects the gaps and never the corrections.
    """
    end = timezone.localdate()
    if days:
        span = max(1, min(int(days), MAX_SYNC_DAYS))
        return end - timedelta(days=span - 1), end

    if connection.synced_through:
        start = connection.synced_through - timedelta(days=OVERLAP_DAYS)
    else:
        start = end - timedelta(days=DEFAULT_BACKFILL_DAYS - 1)

    start = max(start, end - timedelta(days=MAX_SYNC_DAYS - 1))
    return min(start, end), end


def _finish(connection: Connection, report) -> None:
    from . import rollups

    fields = {"last_sync_at": timezone.now(), "last_sync_error": report.stopped_early[:1000]}
    if report.synced_through:
        fields["synced_through"] = report.synced_through
    Connection.objects.filter(pk=connection.pk).update(**fields)

    if report.synced_through:
        # Device rows are authoritative and the rollup leaves them alone; this
        # fills in everything derived from the samples and entries around them.
        start = report.synced_through - timedelta(days=report.days_synced)
        rollups.rebuild(connection.user, start, report.synced_through)

    record_event(
        verb="health.connection.synced",
        actor=connection.user,
        target=connection,
        **report.as_dict(),
    )
