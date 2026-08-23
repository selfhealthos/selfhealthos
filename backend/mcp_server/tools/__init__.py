"""MCP tool modules.

One module per app. Each exposes `register(mcp)`.
"""

from . import health

__all__ = ["health"]


def register_all(mcp) -> None:
    health.register(mcp)
