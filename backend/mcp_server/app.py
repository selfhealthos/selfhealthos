"""MCP endpoint, served over Streamable HTTP at /mcp.

Transport choice: stdio is not an option here. stdio means the client spawns
the server as a local child process and talks over its pipes, which cannot
reach another machine - self-hosters run this in its own container, possibly
on a different machine from the one running Claude Code. Streamable HTTP lets
Claude Code talk to this service over the LAN (plain HTTP works fine - no TLS
is required for the MCP transport itself), and it behaves identically in dev.

Every request needs a bearer token issued by apps/tokens, and each tool
declares the scope it requires - so a read-only token cannot see the write
tools in `tools/list`, let alone call them.

MCP_REQUIRE_AUTH=false disables the requirement for a transition period. It
logs a warning on every request, because an MCP endpoint open to the network
is exactly the thing this closes.
"""

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server import django_setup

django_setup.setup()

# Django is configured from here on, so app and settings imports are safe.
from django.conf import settings  # noqa: E402
from mcp.server import MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from selfhealthos import __version__  # noqa: E402

logger = logging.getLogger(__name__)


def env_bool(name: str, default: bool) -> bool:
    import os

    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", ""}


mcp = MCPServer(
    name="selfhealthos",
    version=__version__,
    instructions=(
        "Self-hosted nutrition and fitness tracker. Call health_describe first "
        "to see which metrics hold data and over what period before reaching "
        "for a more specific tool."
    ),
)


from mcp_server.auth import ScopeMiddleware, TokenAuthMiddleware  # noqa: E402
from mcp_server.tools import register_all  # noqa: E402

register_all(mcp)

# Innermost, so it runs after the SDK's own request-state boundary has built
# the context and can still see the raw method and params.
mcp.middleware.append(ScopeMiddleware())


@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def healthz(request: Request) -> JSONResponse:
    """Container healthcheck. Deliberately outside the MCP protocol."""
    return JSONResponse({"status": "ok", "version": __version__})


#: Names this service answers to from inside the compose network, where there
#: is no reverse proxy in front of it and no TLS (see CLAUDE.md). Anything
#: talking to it internally by service name needs to be listed here, or DNS-
#: rebinding protection rejects it as a Host header matching nothing in
#: ALLOWED_HOSTS.
INTERNAL_HOSTS = ("mcp", "mcp:8080", "127.0.0.1:8080", "localhost:8080")


def _transport_security() -> TransportSecuritySettings:
    """DNS-rebinding protection, driven by the same allow-list as Django.

    The SDK enables this by default with an *empty* allow-list, which rejects
    every request that arrives with a real Host header. Reusing Django's
    settings keeps one source of truth.

    Naming an internal host is not a hole: DNS rebinding is an attack on a
    *browser*, which resolves a name the attacker controls to a private
    address. `mcp` resolves only on the compose network, and nothing outside
    it can reach this port at all - the service publishes none by default.
    """
    hosts: list[str] = []
    for host in settings.ALLOWED_HOSTS:
        hosts.append(host)
        hosts.append(f"{host}:443")
    hosts.extend(INTERNAL_HOSTS)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=list(settings.CSRF_TRUSTED_ORIGINS),
    )


# This app *is* the ASGI application, not something mounted inside another one.
# That matters: Starlette does not run a mounted app's lifespan, and the MCP
# session manager lives in it.
app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    transport_security=_transport_security(),
)

# Outermost: authentication happens before any MCP framing is parsed, so an
# unauthenticated caller gets a plain 401 rather than a protocol-level error.
app = TokenAuthMiddleware(app, required=env_bool("MCP_REQUIRE_AUTH", True))
