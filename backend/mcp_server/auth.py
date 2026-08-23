"""Authentication and scope enforcement for the MCP endpoint.

Two layers, because they answer different questions.

The ASGI layer answers "who is this?". It runs before any MCP framing exists,
rejects an unauthenticated caller with a plain 401, and puts the caller's
scopes somewhere the protocol layer can find them.

The protocol layer answers "may they do this?". It sees `tools/list` and
`tools/call` as such, so it can hide a tool a caller may not use and refuse the
call if they try anyway. That distinction is the point: a read-only token
should not be able to *see* the write tools, let alone invoke them.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import replace

from mcp.shared.exceptions import MCPError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

#: Key under which the ASGI layer stashes resolved scopes on the connection
#: scope. The protocol layer reads them back off `ctx.request`.
#:
#: Not a ContextVar: the two layers are separated by the session manager, which
#: dispatches into its own anyio task group, so the context the ASGI middleware
#: sets is not the context the handler runs in. Measured, not assumed - with a
#: ContextVar every token saw every tool. The ASGI scope dict is the one thing
#: guaranteed to travel with the request.
SCOPE_KEY = "selfhealthos_mcp_scopes"
NAME_KEY = "selfhealthos_mcp_token_name"
USER_KEY = "selfhealthos_mcp_user_id"

#: The token holder, for tools that answer "my" questions.
#:
#: A ContextVar works *here* where it did not between the ASGI and protocol
#: layers, and the difference is worth stating: middleware sets this and then
#: awaits `call_next`, so the tool runs inside the same task and inherits the
#: context. The ASGI boundary crosses into the session manager's own task
#: group, which is why scopes travel on the scope dict instead.
_user_id: ContextVar[str | None] = ContextVar("mcp_user_id", default=None)

#: Retained only as a fallback for a request that somehow arrives without an
#: HTTP scope attached; it should never be the thing that grants access.
_scopes: ContextVar[frozenset[str]] = ContextVar("mcp_scopes", default=frozenset())
_token_name: ContextVar[str] = ContextVar("mcp_token_name", default="")

#: Reachable without a token. The healthcheck is not part of the protocol and
#: the container has no credential to present.
PUBLIC_PATHS = {"/healthz"}

#: JSON-RPC application error. Distinct from a transport 401: by this point the
#: caller *is* authenticated, they simply hold the wrong scope.
FORBIDDEN = -32003


def current_scopes() -> frozenset[str]:
    return _scopes.get()


def _unauthorised(detail: str) -> JSONResponse:
    return JSONResponse(
        {"error": "unauthorized", "detail": detail},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="selfhealthos"'},
    )


class TokenAuthMiddleware:
    """Require a live access token on every MCP request."""

    def __init__(self, app: ASGIApp, *, required: bool = True):
        self.app = app
        self.required = required

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        presented = ""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                presented = value.decode("latin-1")
                break

        token = None
        if presented.lower().startswith("bearer "):
            token = await _resolve(presented[7:].strip())

        if token is None:
            if self.required:
                await _unauthorised("A valid bearer token is required.")(scope, receive, send)
                return
            # Permissive mode exists for the transition only, and says so.
            logger.warning("unauthenticated MCP request to %s allowed", scope.get("path"))
            granted, name = frozenset(), ""
        else:
            granted, name = frozenset(token["scopes"]), token["name"]

        scope[SCOPE_KEY] = granted
        scope[NAME_KEY] = name
        scope[USER_KEY] = token["user_id"] if token else None
        _scopes.set(granted)
        _token_name.set(name)

        await self.app(scope, receive, send)


async def _resolve(presented: str) -> dict | None:
    """Look the token up off the event loop - the ORM is synchronous."""
    from mcp_server.django_setup import run_orm

    def _lookup() -> dict | None:
        from apps.tokens.models import AccessToken

        token = AccessToken.authenticate(presented)
        if token is None:
            return None
        token.touch()
        return {
            "scopes": list(token.scopes or []),
            "name": token.name,
            "user_id": str(token.user_id),
        }

    return await run_orm(_lookup)


class ScopeMiddleware:
    """Filter `tools/list` and gate `tools/call` on the caller's scopes.

    Implemented as SDK middleware rather than by inspecting raw JSON at the
    ASGI layer, because `tools/list` needs its *response* filtered - and over
    Streamable HTTP that response may be an SSE stream, which is not something
    to be rewriting mid-flight.
    """

    @staticmethod
    def _held(ctx) -> frozenset[str]:
        request = getattr(ctx, "request", None)
        asgi_scope = getattr(request, "scope", None)
        if isinstance(asgi_scope, dict) and SCOPE_KEY in asgi_scope:
            return asgi_scope[SCOPE_KEY]
        return current_scopes()

    async def __call__(self, ctx, call_next):
        from mcp_server.registry import TOOL_SCOPES

        # Set before call_next so the tool, which runs inside it, inherits it.
        _user_id.set(self._user(ctx))

        if ctx.method == "tools/call":
            held = self._held(ctx)
            name = (ctx.params or {}).get("name")
            required = TOOL_SCOPES.get(name)
            if required and required not in held:
                logger.warning("token %r denied %s (needs %s)", self._name(ctx), name, required)
                raise MCPError(
                    FORBIDDEN,
                    f"This token does not hold the {required!r} scope required by {name!r}.",
                )
            return await call_next(ctx)

        result = await call_next(ctx)

        if ctx.method == "tools/list":
            result = self._filter_tools(result, self._held(ctx), TOOL_SCOPES)
        return result

    @staticmethod
    def _user(ctx) -> str | None:
        request = getattr(ctx, "request", None)
        asgi_scope = getattr(request, "scope", None)
        if isinstance(asgi_scope, dict):
            return asgi_scope.get(USER_KEY)
        return None

    @staticmethod
    def _name(ctx) -> str:
        request = getattr(ctx, "request", None)
        asgi_scope = getattr(request, "scope", None)
        if isinstance(asgi_scope, dict):
            return asgi_scope.get(NAME_KEY, "")
        return _token_name.get()

    @staticmethod
    def _filter_tools(result, held: frozenset[str], tool_scopes: dict[str, str]):
        """Drop tools the caller has no scope for.

        The SDK hands this back as a plain dict at this point in the chain, not
        the pydantic model the type hints suggest - so both shapes are handled
        rather than assumed. Getting that wrong fails silently: every tool
        stays visible and nothing errors.
        """
        as_dict = isinstance(result, dict)
        tools = result.get("tools") if as_dict else getattr(result, "tools", None)
        if not tools:
            return result

        def permitted(tool) -> bool:
            name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
            required = tool_scopes.get(name)
            return required is None or required in held

        allowed = [tool for tool in tools if permitted(tool)]
        if len(allowed) == len(tools):
            return result
        if as_dict:
            return {**result, "tools": allowed}
        try:
            return result.model_copy(update={"tools": allowed})
        except AttributeError:
            return replace(result, tools=allowed)


def current_user_id() -> str | None:
    """The token holder's id, for tools that answer "my" questions."""
    return _user_id.get()


def require_user():
    """The token holder, or a refusal.

    Health data is one person's. A tool that cannot say whose data it is being
    asked about must decline rather than guess or answer for everybody.
    """
    from apps.accounts.models import User

    user_id = current_user_id()
    if not user_id:
        raise MCPError(FORBIDDEN, "This tool needs a token identifying whose data to read.")
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise MCPError(FORBIDDEN, "The token's owner no longer exists.")
    return user
