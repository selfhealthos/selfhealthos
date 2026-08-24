"""The scope vocabulary.

One string per capability, `<domain>:<action>`. Scopes are the only thing
that distinguishes one non-browser client from another - a token generated
for Claude Code carries exactly the capability its holder was granted.

Adding a scope here and to `mcp_server/registry.py` is the whole of granting
a new capability.
"""

from __future__ import annotations

from dataclasses import dataclass

READ = "read"
WRITE = "write"


@dataclass(frozen=True)
class Scope:
    key: str
    label: str
    description: str


SCOPES: tuple[Scope, ...] = (
    Scope("health:read", "Health — read", "Metrics, days, trends, sleep, food, habits."),
    Scope("health:write", "Health — write", "Add or correct health entries."),
    Scope("social:read", "Friends — read", "Your friends list and pending friend requests."),
    Scope(
        "social:write",
        "Friends — write",
        "Send, accept and decline friend requests, and log workouts you did together.",
    ),
)

BY_KEY: dict[str, Scope] = {s.key: s for s in SCOPES}
ALL: frozenset[str] = frozenset(BY_KEY)

#: Sensible bundles, offered in the UI so the common cases are one click.
PRESETS: dict[str, tuple[str, ...]] = {
    # Claude Code / MCP. Read everything, change nothing, unless the holder
    # explicitly asks for write too.
    #
    # No social:* in either Claude preset, and no MCP tool reads the friend
    # graph: MCP is deliberately self-only. An agent that can enumerate who
    # you know - or write a workout into their log - is a much larger grant
    # than "answer questions about my own health data", and nothing about the
    # MCP use case needs it.
    "claude": ("health:read",),
    "claude-write": ("health:read", "health:write"),
    "read-only": ("health:read", "social:read"),
    "full-access": ("health:read", "health:write", "social:read", "social:write"),
}


def normalise(scopes) -> list[str]:
    """Deduplicate, drop unknown scopes, and return in a stable order."""
    wanted = {s.strip() for s in scopes if s and s.strip()}
    return [s.key for s in SCOPES if s.key in wanted]


def unknown(scopes) -> list[str]:
    return sorted({s.strip() for s in scopes if s and s.strip()} - ALL)
