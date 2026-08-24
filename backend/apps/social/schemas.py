from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ninja import Schema


class SocialUserOut(Schema):
    """The one shape any API returns for "a person who is not the caller".

    Five call sites already: the friends list, both request lists, the workout
    picker, and - once the timeline lands - post and comment authors. Defined
    once so the timeline reuses it instead of inventing a second user card.

    Deliberately minimal. The friend graph grants no cross-user reads, so
    nothing here is anything the holder did not already publish as their
    identity on the instance.
    """

    id: UUID
    username: str
    avatar_url: str | None = None


class SocialFriendOut(Schema):
    """An accepted friend, plus the caller's own settings about them."""

    user: SocialUserOut
    friendship_id: UUID
    #: The caller's setting, never the friend's. See FriendPref.
    workout_partner: bool
    #: The friend's own switch, shown so the picker can explain a name that is
    #: present but cannot be ticked.
    accepts_partner_logging: bool
    since: datetime | None = None


class SocialRequestOut(Schema):
    friendship_id: UUID
    user: SocialUserOut
    created_at: datetime


class SocialRequestsOut(Schema):
    incoming: list[SocialRequestOut]
    outgoing: list[SocialRequestOut]


class SocialFriendRequestIn(Schema):
    username: str | None = None
    friend_code: str | None = None


class SocialRequestAckOut(Schema):
    """Deliberately uninformative on the miss path.

    `sent` is false for "no such user", "they have username discovery off" and
    "they blocked you" alike; `state` never distinguishes them. See
    `services.send_request`.
    """

    sent: bool
    state: str
    friendship_id: UUID | None = None


class SocialPrefsIn(Schema):
    workout_partner: bool


class SocialMeOut(Schema):
    """The caller's own social settings, for the Settings page."""

    friend_code: str
    discoverable_by_username: bool
    allow_partner_logging: bool


class SocialMeIn(Schema):
    discoverable_by_username: bool | None = None
    allow_partner_logging: bool | None = None
