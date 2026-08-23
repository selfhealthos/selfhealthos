"""Boot Django inside the MCP process.

The MCP server runs as its own container but imports the same Django service
layer as the REST API - no HTTP hop, no duplicated logic. This must be imported
(and ``setup()`` called) before anything touches models or settings.
"""

import os


def setup() -> None:
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "selfhealthos.settings.dev")
    django.setup()


async def run_orm(func, /, *args, **kwargs):
    """Run a synchronous service call off the event loop.

    MCP tool handlers are async; the Django ORM is synchronous. Each worker
    thread opens its own connection, so stale ones are closed afterwards to
    keep the pool from growing with every tool call.
    """
    import asyncio

    from django.db import close_old_connections

    def _call():
        close_old_connections()
        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()

    return await asyncio.to_thread(_call)
