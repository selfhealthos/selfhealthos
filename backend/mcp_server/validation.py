"""Reject tool arguments the tool does not declare.

The SDK builds each tool's argument model from its signature, and pydantic's
default is to *ignore* a key the model has no field for. So a caller that
guesses a plausible-but-wrong argument name gets a successful response
computed from the defaults, with nothing anywhere saying the argument was
dropped.

That is not theoretical. `health_day` took `on`; a caller asked for `date`,
the key was discarded, and the tool fell back to its "latest day with data"
default - returning today, six times in a row, for six different dates. It
reads as a tool ignoring its own argument, and there is no error to chase.

Better to fail loudly with the accepted names in the message.
"""

from __future__ import annotations

import logging

from mcp.shared.exceptions import MCPError

logger = logging.getLogger(__name__)

#: JSON-RPC invalid params. The call is well-formed protocol, badly-formed
#: arguments - which is exactly what this is.
INVALID_PARAMS = -32602


class StrictArgumentsMiddleware:
    """Fail a `tools/call` carrying arguments the tool does not accept."""

    def __init__(self, mcp):
        self._mcp = mcp

    def _accepted(self, name: str) -> set[str] | None:
        """Declared argument names, or None if the tool cannot be resolved."""
        try:
            tool = self._mcp._tool_manager.get_tool(name)
        except Exception:  # unknown tool - let the SDK produce its own error
            return None
        if tool is None:
            return None
        schema = getattr(tool, "parameters", None) or {}
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return None
        return set(properties)

    async def __call__(self, ctx, call_next):
        if ctx.method == "tools/call":
            params = ctx.params or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            accepted = self._accepted(name) if isinstance(arguments, dict) else None
            if accepted is not None:
                unknown = sorted(set(arguments) - accepted)
                if unknown:
                    logger.warning("%s called with unknown arguments %s", name, unknown)
                    raise MCPError(
                        INVALID_PARAMS,
                        f"{name!r} does not accept {', '.join(repr(u) for u in unknown)}. "
                        f"It accepts: {', '.join(sorted(accepted)) or 'no arguments'}.",
                    )
        return await call_next(ctx)
