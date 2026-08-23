"""Token management, and device/agent enrolment.

Two audiences. A signed-in human manages their own tokens from Settings; a
non-browser client (a future mobile app, a script) enrols itself once with
the account password - which it then never stores.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.contrib.auth import authenticate
from django.core.cache import cache
from ninja import Router, Schema, Status

from apps.core.exceptions import DomainError
from apps.core.services import record_event

from . import scopes as scope_defs
from .auth import client_ip
from .models import AccessToken

router = Router(tags=["tokens"])

#: Enrolment is the only endpoint a non-browser can reach with a password, so
#: it is the only one worth throttling by hand.
ENROL_MAX_ATTEMPTS = 10
ENROL_WINDOW_S = 900


class InvalidCredentials(DomainError):
    status_code = 401
    title = "Sign in failed"


class TooManyAttempts(DomainError):
    status_code = 429
    title = "Too many attempts"


class UnknownScopes(DomainError):
    status_code = 400
    title = "Unknown scopes"


class ScopeOut(Schema):
    key: str
    label: str
    description: str


class TokenOut(Schema):
    id: str
    name: str
    kind: str
    masked: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    revoked_at: datetime | None = None
    is_live: bool


class TokenCreatedOut(TokenOut):
    #: Returned once, on creation, and never again. There is no endpoint that
    #: can show it later - the database holds only a hash.
    secret: str


class CreateTokenIn(Schema):
    name: str
    scopes: list[str] = []
    preset: str | None = None
    kind: str = AccessToken.Kind.DEVICE


class EnrolIn(Schema):
    username: str
    password: str
    device_name: str
    preset: str = "full-access"


def _out(token: AccessToken) -> dict:
    return {
        "id": str(token.pk),
        "name": token.name,
        "kind": token.kind,
        "masked": token.masked,
        "scopes": token.scopes or [],
        "created_at": token.created_at,
        "expires_at": token.expires_at,
        "last_used_at": token.last_used_at,
        "last_used_ip": token.last_used_ip,
        "revoked_at": token.revoked_at,
        "is_live": token.is_live,
    }


def _resolve_scopes(payload_scopes: list[str], preset: str | None) -> list[str]:
    requested = list(payload_scopes)
    if preset:
        requested += list(scope_defs.PRESETS.get(preset, ()))
    bad = scope_defs.unknown(requested)
    if bad:
        raise UnknownScopes(f"Not a known scope: {', '.join(bad)}")
    return scope_defs.normalise(requested)


@router.get("/scopes", response=list[ScopeOut], operation_id="listScopes")
def list_scopes(request):
    return [
        {"key": s.key, "label": s.label, "description": s.description} for s in scope_defs.SCOPES
    ]


@router.get("", response=list[TokenOut], operation_id="listTokens")
def list_tokens(request):
    return [_out(t) for t in AccessToken.objects.for_user(request.auth)]


@router.post("", response={201: TokenCreatedOut}, operation_id="createToken")
def create_token(request, payload: CreateTokenIn):
    token, secret = AccessToken.issue(
        user=request.auth,
        name=payload.name,
        scopes=_resolve_scopes(payload.scopes, payload.preset),
        kind=payload.kind,
    )
    record_event(
        verb="token.issued",
        actor=request.auth,
        target=token,
        name=token.name,
        scopes=token.scopes,
    )
    return Status(201, {**_out(token), "secret": secret})


@router.post(
    "/enrol",
    response={201: TokenCreatedOut},
    auth=None,
    operation_id="enrolDevice",
)
def enrol(request, payload: EnrolIn):
    """Trade a username and password for a device token, once.

    The password is used here and never stored on the device: what it holds
    afterwards is a token, revocable on its own, so a lost device costs one
    row rather than a password change everywhere.
    """
    ip = client_ip(request) or "unknown"
    key = f"enrol:{ip}"
    attempts = cache.get(key, 0)
    if attempts >= ENROL_MAX_ATTEMPTS:
        raise TooManyAttempts("Too many enrolment attempts. Try again later.")
    cache.set(key, attempts + 1, ENROL_WINDOW_S)

    user = authenticate(request, username=payload.username.strip(), password=payload.password)
    if user is None:
        raise InvalidCredentials("That username and password combination was not recognised.")

    cache.delete(key)
    token, secret = AccessToken.issue(
        user=user,
        name=payload.device_name,
        scopes=_resolve_scopes([], payload.preset),
        kind=AccessToken.Kind.DEVICE,
    )
    record_event(
        verb="token.enrolled",
        actor=user,
        target=token,
        name=token.name,
        scopes=token.scopes,
        ip=ip,
    )
    return Status(201, {**_out(token), "secret": secret})


# Declared last, and typed as a UUID rather than a string, so a literal path
# segment can never be mistaken for an id. Registered before /enrol, `str` made
# "/tokens/enrol" match this route, and POST to it returned 405 rather than
# enrolling anything.
@router.delete("/{uuid:token_id}", response={204: None}, operation_id="revokeToken")
def revoke_token(request, token_id: UUID):
    token = AccessToken.objects.for_user(request.auth).filter(pk=token_id).first()
    if token is None:
        raise DomainError("No such token.")
    token.revoke()
    record_event(verb="token.revoked", actor=request.auth, target=token, name=token.name)
    return Status(204, None)
