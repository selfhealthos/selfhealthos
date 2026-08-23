"""Tool registration with scope declarations.

Every tool states the scope it needs at definition time, so `tools/list`
filters on this map and a read-only token stops being able to *see* the write
tools, let alone call them. Recording the scope here means adding a new
capability touches this file and not every tool.
"""

from __future__ import annotations

from collections.abc import Callable

#: tool name -> required scope, e.g. {"health_log": "health:write"}
TOOL_SCOPES: dict[str, str] = {}


def scoped_tool(mcp, *, scope: str, **tool_kwargs) -> Callable:
    """Register an MCP tool and record the scope it will require."""

    def decorator(func: Callable) -> Callable:
        TOOL_SCOPES[func.__name__] = scope
        return mcp.tool(**tool_kwargs)(func)

    return decorator


def tools_for_scopes(scopes: set[str]) -> set[str]:
    """Tool names a caller holding `scopes` may use."""
    return {name for name, required in TOOL_SCOPES.items() if required in scopes}
