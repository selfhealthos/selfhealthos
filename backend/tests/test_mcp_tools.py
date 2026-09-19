"""MCP tool behaviour, pinned at the failure modes that actually bit.

Both of these produced a confident, wrong-looking answer rather than an error,
which is the expensive kind of bug: the caller cannot tell the tool misfired.
"""

from __future__ import annotations

import datetime as dt

import pytest
from asgiref.sync import async_to_sync
from mcp.shared.exceptions import MCPError

from apps.health.models import DietEntry, Note
from mcp_server import auth
from mcp_server.app import mcp
from mcp_server.validation import StrictArgumentsMiddleware


def call(name: str, user, /, **kwargs):
    """Invoke a registered tool as the given token holder."""
    auth._user_id.set(str(user.pk))
    return async_to_sync(mcp._tool_manager.get_tool(name).fn)(**kwargs)


@pytest.fixture
def diary(user):
    """Two days of entries, so "the day I asked for" is distinguishable."""
    for day, name in (
        (dt.date(2026, 9, 15), "sardines and potatoes"),
        (dt.date(2026, 9, 19), "oatmeal"),
    ):
        DietEntry.objects.create(
            created_by=user,
            name=name,
            local_date=day,
            occurred_at=dt.datetime.combine(day, dt.time(12), tzinfo=dt.UTC),
        )
    Note.objects.create(
        created_by=user,
        title="knee",
        content="knee felt fine",
        local_date=dt.date(2026, 9, 15),
        occurred_at=dt.datetime(2026, 9, 15, 12, tzinfo=dt.UTC),
    )
    return user


@pytest.mark.django_db(transaction=True)
def test_health_day_honours_the_date_argument(diary):
    """`date` was silently dropped, so every day returned the latest one."""
    day = call("health_day", diary, date="2026-09-15")
    assert day.date == "2026-09-15"
    assert [e.summary for e in day.food] == ["sardines and potatoes"]


@pytest.mark.django_db(transaction=True)
def test_health_day_still_accepts_the_on_alias(diary):
    assert call("health_day", diary, on="2026-09-15").date == "2026-09-15"


@pytest.mark.django_db(transaction=True)
def test_health_day_rejects_two_disagreeing_days(diary):
    with pytest.raises(ValueError, match="both given"):
        call("health_day", diary, date="2026-09-15", on="2026-09-19")


@pytest.mark.django_db(transaction=True)
def test_health_day_rejects_a_non_date(diary):
    with pytest.raises(ValueError, match="ISO date"):
        call("health_day", diary, date="last tuesday")


@pytest.mark.django_db(transaction=True)
def test_health_search_wildcard_returns_everything(diary):
    """`*` matched nothing literally, which reads as "you have no data"."""
    result = call("health_search", diary, query="*")
    assert result.matched == 3
    assert {h.text for h in result.hits} == {"sardines and potatoes", "oatmeal", "knee felt fine"}


@pytest.mark.django_db(transaction=True)
def test_health_search_still_filters_on_real_text(diary):
    result = call("health_search", diary, query="sardines")
    assert [h.text for h in result.hits] == ["sardines and potatoes"]


@pytest.mark.django_db(transaction=True)
def test_health_search_rejects_an_empty_query(diary):
    with pytest.raises(ValueError, match="search for"):
        call("health_search", diary, query="   ")


class _Ctx:
    def __init__(self, arguments):
        self.method = "tools/call"
        self.params = {"name": "health_day", "arguments": arguments}


def _run(arguments):
    async def call_next(ctx):
        return "reached the tool"

    return async_to_sync(StrictArgumentsMiddleware(mcp).__call__)(_Ctx(arguments), call_next)


def test_unknown_arguments_are_refused_not_dropped():
    with pytest.raises(MCPError) as caught:
        _run({"whenever": "2026-09-15"})
    assert "'whenever'" in str(caught.value)
    assert "date" in str(caught.value)


def test_declared_arguments_pass_through():
    assert _run({"date": "2026-09-15"}) == "reached the tool"


BLOCKS = '[{"t":"text","v":"slept a lot last night, have been sick this week and had a day off"}]'


@pytest.fixture
def blocky_note(user):
    """A note as the Android app writes it: block JSON, title a 60-char prefix."""
    Note.objects.create(
        created_by=user,
        title="slept a lot last night, have been sick this week and had a d",
        content=BLOCKS,
        local_date=dt.date(2026, 9, 14),
        occurred_at=dt.datetime(2026, 9, 14, 12, tzinfo=dt.UTC),
    )
    return user


@pytest.mark.django_db(transaction=True)
def test_health_day_returns_the_whole_note(blocky_note):
    """The title is a truncated prefix; reporting it loses the sentence."""
    (note,) = call("health_day", blocky_note, date="2026-09-14").notes
    assert note.summary.endswith("had a day off")
    assert '"t":"text"' not in note.summary


@pytest.mark.django_db(transaction=True)
def test_health_search_returns_the_whole_note(blocky_note):
    (hit,) = call("health_search", blocky_note, query="sick").hits
    assert hit.text.endswith("had a day off")
    assert '"t":"text"' not in hit.text


@pytest.mark.django_db(transaction=True)
def test_untitled_note_is_not_raw_block_json(user):
    Note.objects.create(
        created_by=user,
        title="",
        content=BLOCKS,
        local_date=dt.date(2026, 9, 14),
        occurred_at=dt.datetime(2026, 9, 14, 12, tzinfo=dt.UTC),
    )
    (note,) = call("health_day", user, date="2026-09-14").notes
    assert note.summary.startswith("slept a lot")
