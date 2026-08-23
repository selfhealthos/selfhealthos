"""Bearer authentication for django-ninja.

Routers take `auth=[django_auth, TokenAuth()]`, so one endpoint serves both the
browser's session cookie and a token-holding client without branching. Whatever
authenticates, `request.auth` ends up as the user - the routers never learn
which it was.
"""

from __future__ import annotations

import logging

from ninja.security import HttpBearer, SessionAuth

from apps.core.exceptions import DomainError

from .models import AccessToken

logger = logging.getLogger(__name__)


def client_ip(request) -> str | None:
    """The caller's address, if anything upstream actually says.

    The Next.js frontend's rewrite proxy (see frontend/next.config.ts) does not
    set X-Forwarded-For, so this falls back to REMOTE_ADDR in practice - which
    is Next's own container address, not the browser's, since django has no
    published port and nothing but Next can reach it on the compose network.
    That still makes the one caller of this function (device/agent enrolment's
    rate limit) an effective global throttle rather than a per-caller one, not
    a spoofable one: REMOTE_ADDR is set by the TCP connection, not a header,
    so it cannot be forged by a request body or header value either way. If
    you front this with your own reverse proxy that *does* set
    X-Forwarded-For, that header is honoured first.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def presents_bearer(request) -> bool:
    return request.META.get("HTTP_AUTHORIZATION", "").lower().startswith("bearer ")


class SessionAuthUnlessBearer(SessionAuth):
    """`django_auth`, standing aside when the caller presents a bearer token.

    ninja's `SessionAuth` runs the CSRF check inside `_get_key`, *before* it
    looks for a session cookie, and raises 403 outright when it fails. With
    `auth=[django_auth, TokenAuth()]` that means an unsafe request carrying only
    a bearer token - no cookies at all - is rejected as a CSRF failure and
    `TokenAuth` is never reached. Every GET worked, so the hole stayed invisible
    until the phone's first POST.

    Declining here is correct rather than merely convenient. CSRF defends
    against a browser attaching an *ambient* credential to a request some other
    site triggered. A token that has to be set explicitly on the Authorization
    header is never ambient: an attacker who can set it does not need the
    victim's browser. So a request bearing one is not the thing CSRF protects
    against, and session auth has no business judging it.

    Overriding `__call__` rather than `_get_key`: skipping only the key lookup
    would still leave `authenticate()` reading `request.user`, which ignores
    the key entirely and answers from the session. A request presenting a bogus
    token alongside a valid cookie would then be authenticated by the cookie -
    an explicit credential that is wrong must be an error, not an invitation to
    fall back on whatever else was attached. Declining outright sends it to
    `TokenAuth`, which refuses it with 401.
    """

    def __call__(self, request):
        if presents_bearer(request):
            return None
        return super().__call__(request)


class TokenAuth(HttpBearer):
    """Authenticate `Authorization: Bearer shos_pat_…`."""

    def authenticate(self, request, token: str):
        access = AccessToken.authenticate(token)
        if access is None:
            return None

        access.touch(ip=client_ip(request))
        # Both are set: `request.auth` is what ninja hands the view, and
        # `request.user` keeps `created_by=` and the audit log working for code
        # that has no idea a token was involved.
        request.user = access.user
        request.access_token = access
        return access.user


def scopes_for(request) -> set[str]:
    """Scopes the caller holds.

    A session-authenticated human is not scope-limited: they logged in with a
    password and can already do anything through the UI, so constraining them
    here would be theatre. Scopes exist to narrow *machines*.
    """
    access = getattr(request, "access_token", None)
    if access is not None:
        return set(access.scopes or [])
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        from . import scopes as scope_defs

        return set(scope_defs.ALL)
    return set()


class InsufficientScope(DomainError):
    status_code = 403
    title = "Insufficient scope"


def require_scope(request, scope: str) -> None:
    """Gate an endpoint on one capability, or raise.

    403 rather than 401: the credential is valid and re-authenticating will not
    help. What is needed is a token issued with a different scope, and saying
    so by status code is the difference between a client that re-enrols in a
    loop and one that surfaces the problem.
    """
    if scope in scopes_for(request):
        return
    raise InsufficientScope(
        f"This credential does not carry the {scope!r} scope.", required_scope=scope
    )
