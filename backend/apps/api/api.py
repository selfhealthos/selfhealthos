"""The single NinjaAPI instance.

Every app contributes a router here. Routers stay thin - they validate input,
call a service function, and shape the response. Business logic never lives in
this layer, because the MCP tools call the same services and the two must not
be able to drift.
"""

from ninja import NinjaAPI

from apps.accounts.api import router as auth_router
from apps.fitness.api import router as fitness_router
from apps.health.api import router as health_router
from apps.social.api import router as social_router
from apps.tokens.api import router as tokens_router
from apps.tokens.auth import SessionAuthUnlessBearer, TokenAuth
from selfhealthos import __version__

from .errors import register_exception_handlers
from .routers.healthz import router as healthz_router

api = NinjaAPI(
    title="selfhealthos API",
    version=__version__,
    description=(
        "Self-hosted nutrition and fitness tracker. "
        "The same service layer backs the MCP endpoint at /mcp."
    ),
    urls_namespace="api-v1",
    # Authenticated by default; endpoints that must be reachable without a
    # session opt out explicitly with auth=None. Failing closed means a new
    # router cannot accidentally be public.
    #
    # Two schemes, tried in order. The session scheme carries csrf=True, so a
    # browser still needs an X-CSRFToken header on unsafe methods. Bearer
    # tokens are exempt from CSRF by construction: CSRF defends against a
    # browser attaching an *ambient* credential to a cross-site request, and a
    # token that must be set explicitly on the Authorization header is never
    # ambient.
    #
    # `SessionAuthUnlessBearer` rather than ninja's `django_auth` is what makes
    # that second sentence true. See its docstring - the stock class runs the
    # CSRF check before it looks for a cookie, which rejected token-authenticated
    # POSTs outright.
    auth=[SessionAuthUnlessBearer(), TokenAuth()],
)

register_exception_handlers(api)

# The liveness probe lives at /healthz, not /health: it is infrastructure, and
# the Health app has the better claim on the readable path. /healthz is also
# what the MCP container exposes for the same purpose.
api.add_router("/healthz", healthz_router)
api.add_router("/auth", auth_router)
api.add_router("/tokens", tokens_router)
api.add_router("/health", health_router)
api.add_router("/fitness", fitness_router)
api.add_router("/social", social_router)
