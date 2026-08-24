"""REST surface for the friend graph.

Thin over `services`, like every other router here - which matters more than
usual for this app, because `services` is also where the deferred timeline
will ask its permission questions. Anything decided in this file instead of
there is a decision the timeline would have to reimplement.
"""

from __future__ import annotations

from uuid import UUID

from ninja import Router, Status

from apps.social import services

from .schemas import (
    SocialFriendOut,
    SocialFriendRequestIn,
    SocialMeIn,
    SocialMeOut,
    SocialPrefsIn,
    SocialRequestAckOut,
    SocialRequestsOut,
)

router = Router(tags=["social"])


@router.get(
    "/me",
    response=SocialMeOut,
    summary="Your own friend code and discovery settings",
    operation_id="getSocialSettings",
)
def get_settings(request):
    return services.social_settings(request.auth)


@router.patch(
    "/me",
    response=SocialMeOut,
    summary="Update your discovery and shared-workout settings",
    operation_id="updateSocialSettings",
)
def update_settings(request, payload: SocialMeIn):
    return services.update_social_settings(
        request.auth,
        discoverable_by_username=payload.discoverable_by_username,
        allow_partner_logging=payload.allow_partner_logging,
    )


@router.post(
    "/me/friend-code",
    response=SocialMeOut,
    summary="Mint a new friend code, invalidating the old one",
    operation_id="rotateFriendCode",
)
def rotate_code(request):
    services.rotate_friend_code(request.auth)
    return services.social_settings(request.auth)


@router.get(
    "/friends",
    response=list[SocialFriendOut],
    summary="Your accepted friends",
    operation_id="listFriends",
)
def list_friends(request):
    return services.friend_rows(request.auth)


@router.delete(
    "/friends/{user_id}",
    response={204: None},
    summary="Remove a friend",
    operation_id="unfriend",
)
def unfriend(request, user_id: UUID):
    services.unfriend(request.auth, user_id)
    return Status(204, None)


@router.patch(
    "/friends/{user_id}/prefs",
    response=SocialFriendOut,
    summary="Your own settings about one friend",
    operation_id="updateFriendPrefs",
)
def update_prefs(request, user_id: UUID, payload: SocialPrefsIn):
    services.set_prefs(request.auth, user_id, workout_partner=payload.workout_partner)
    return next(row for row in services.friend_rows(request.auth) if row["user"]["id"] == user_id)


@router.post(
    "/friends/{user_id}/block",
    response={204: None},
    summary="Block a user",
    operation_id="blockUser",
)
def block(request, user_id: UUID):
    services.block(request.auth, user_id)
    return Status(204, None)


@router.delete(
    "/friends/{user_id}/block",
    response={204: None},
    summary="Unblock a user",
    operation_id="unblockUser",
)
def unblock(request, user_id: UUID):
    services.unblock(request.auth, user_id)
    return Status(204, None)


@router.get(
    "/friend-requests",
    response=SocialRequestsOut,
    summary="Pending requests, incoming and outgoing",
    operation_id="listFriendRequests",
)
def list_requests(request):
    return services.request_rows(request.auth)


@router.post(
    "/friend-requests",
    response={202: SocialRequestAckOut},
    summary="Ask to be someone's friend, by username or friend code",
    operation_id="sendFriendRequest",
)
def send_request(request, payload: SocialFriendRequestIn):
    """202 whether or not the account exists.

    A 404 here would let anyone confirm who holds an account on this instance
    by watching which usernames come back differently, so the miss path is
    indistinguishable from "they have username discovery off" and from "they
    blocked you". `sent: false` is all the caller learns.
    """
    edge = services.send_request(
        request.auth, username=payload.username, friend_code=payload.friend_code
    )
    if edge is None:
        return Status(202, {"sent": False, "state": "no_action"})
    return Status(202, {"sent": True, "state": edge.status, "friendship_id": edge.pk})


@router.post(
    "/friend-requests/{friendship_id}/accept",
    response=SocialRequestAckOut,
    summary="Accept an incoming request",
    operation_id="acceptFriendRequest",
)
def accept(request, friendship_id: UUID):
    edge = services.accept_request(request.auth, friendship_id)
    return {"sent": True, "state": edge.status, "friendship_id": edge.pk}


@router.post(
    "/friend-requests/{friendship_id}/decline",
    response={204: None},
    summary="Decline an incoming request",
    operation_id="declineFriendRequest",
)
def decline(request, friendship_id: UUID):
    services.decline_request(request.auth, friendship_id)
    return Status(204, None)


@router.post(
    "/friend-requests/{friendship_id}/cancel",
    response={204: None},
    summary="Withdraw a request you sent",
    operation_id="cancelFriendRequest",
)
def cancel(request, friendship_id: UUID):
    services.cancel_request(request.auth, friendship_id)
    return Status(204, None)
