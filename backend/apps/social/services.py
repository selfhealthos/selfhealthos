"""Everything that decides whether two users may interact.

This module is the only place that answers that question. `apps.fitness` asks
it before logging a workout to somebody else's account; the deferred timeline
will ask it before showing a post or accepting a comment. Blocking is enforced
here, once, rather than in each feature - see `docs/roadmap-social.md`
decision 3.

Routers stay thin over this, like every other app.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from apps.core.exceptions import Conflict, NotFound
from apps.core.services import record_event

from .models import FriendPref, Friendship, Status, generate_friend_code

User = get_user_model()

#: Friend requests one account may send per hour. Generous for a person, and
#: the difference between an instance where one account can quietly ask all 999
#: others and one where it cannot.
REQUEST_LIMIT = 20
REQUEST_WINDOW_S = 3600

#: Attempts to find an unused `friend_code` before giving up. Collisions at
#: ~46 bits are vanishingly rare; the loop exists so that "vanishingly rare"
#: is not the same as "corrupts a signup".
CODE_ATTEMPTS = 5


# --------------------------------------------------------------------------
# The pair key
# --------------------------------------------------------------------------


def ordered_pair(a, b):
    """The two users sorted by primary key - `Friendship`'s canonical order.

    Python's UUID comparison is by 128-bit integer value and Postgres compares
    its `uuid` type bytewise; for UUIDs those orderings are identical, so this
    agrees with the database's own check constraint.
    """
    return (a, b) if a.pk < b.pk else (b, a)


def get_friendship(a, b) -> Friendship | None:
    """The edge between two users, whatever its status, or None."""
    if a is None or b is None or a.pk == b.pk:
        return None
    low, high = ordered_pair(a, b)
    return Friendship.objects.filter(user_low=low, user_high=high).first()


def are_friends(a, b) -> bool:
    edge = get_friendship(a, b)
    return edge is not None and edge.status == Status.ACCEPTED


def friends_of(user):
    """Every user with an accepted edge to `user`, as a queryset of User."""
    if user is None or not getattr(user, "is_authenticated", False):
        return User.objects.none()
    edges = Friendship.objects.involving(user).accepted()
    ids = {edge.user_high_id if edge.user_low_id == user.pk else edge.user_low_id for edge in edges}
    return User.objects.filter(pk__in=ids).order_by("username")


def friend_rows(user) -> list[dict]:
    """The friends list as the API returns it: friend, edge, and my prefs.

    Built in one pass over three queries rather than per-friend lookups - a
    list of 50 friends should not be 50 round trips.
    """
    edges = list(Friendship.objects.involving(user).accepted())
    if not edges:
        return []

    by_other = {(e.user_high_id if e.user_low_id == user.pk else e.user_low_id): e for e in edges}
    others = User.objects.filter(pk__in=by_other).order_by("username")
    pinned = set(
        FriendPref.objects.filter(
            owner=user, friend__in=by_other, workout_partner=True
        ).values_list("friend_id", flat=True)
    )
    return [
        {
            "user": user_card(other),
            "friendship_id": by_other[other.pk].pk,
            "workout_partner": other.pk in pinned,
            "accepts_partner_logging": other.allow_partner_logging,
            "since": by_other[other.pk].responded_at,
        }
        for other in others
    ]


def request_rows(user) -> dict:
    """Pending requests, split by who asked.

    The split comes off `requested_by`, not off the pair columns: those are
    ordered by UUID and carry no direction at all.
    """
    edges = list(Friendship.objects.involving(user).pending().select_related("requested_by"))
    other_ids = {e.user_high_id if e.user_low_id == user.pk else e.user_low_id for e in edges}
    people = {u.pk: u for u in User.objects.filter(pk__in=other_ids)}

    incoming, outgoing = [], []
    for edge in edges:
        other_id = edge.user_high_id if edge.user_low_id == user.pk else edge.user_low_id
        row = {
            "friendship_id": edge.pk,
            "user": user_card(people[other_id]),
            "created_at": edge.created_at,
        }
        (outgoing if edge.requested_by_id == user.pk else incoming).append(row)
    return {"incoming": incoming, "outgoing": outgoing}


def user_card(user) -> dict:
    """`SocialUserOut`'s payload. One shape, one place it is built."""
    return {
        "id": user.pk,
        "username": user.username,
        "avatar_url": user.avatar.url if user.avatar else None,
    }


def social_settings(user) -> dict:
    """The caller's own social settings. Mints a friend code on first read."""
    return {
        "friend_code": ensure_friend_code(user),
        "discoverable_by_username": user.discoverable_by_username,
        "allow_partner_logging": user.allow_partner_logging,
    }


def update_social_settings(user, *, discoverable_by_username=None, allow_partner_logging=None):
    fields = []
    if discoverable_by_username is not None:
        user.discoverable_by_username = discoverable_by_username
        fields.append("discoverable_by_username")
    if allow_partner_logging is not None:
        user.allow_partner_logging = allow_partner_logging
        fields.append("allow_partner_logging")
    if fields:
        user.save(update_fields=fields)
    return social_settings(user)


# --------------------------------------------------------------------------
# Friend codes
# --------------------------------------------------------------------------


def ensure_friend_code(user) -> str:
    """`user`'s friend code, minting one on first use.

    Lazy rather than assigned at signup so that adding this feature needed no
    data migration over existing accounts, and so an instance whose owner never
    opens the friends page never generates one.
    """
    if user.friend_code:
        return user.friend_code
    return rotate_friend_code(user)


def rotate_friend_code(user) -> str:
    """Mint a new code, invalidating the old one.

    Retries on collision rather than trusting the odds: `save()` here can only
    fail on the `friend_code` unique index, since nothing else about the row
    changes.
    """
    for _ in range(CODE_ATTEMPTS):
        candidate = generate_friend_code()
        try:
            with transaction.atomic():
                user.friend_code = candidate
                user.save(update_fields=["friend_code"])
        except IntegrityError:
            continue
        return candidate
    raise Conflict("Could not allocate a friend code. Try again.")


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


def _rate_limit(actor) -> None:
    key = f"social:req:{actor.pk}"
    # add() only sets the key if absent, so the window starts at the first
    # request of the hour and does not slide forward with each one - otherwise
    # a steady trickle would hold the window open indefinitely.
    cache.add(key, 0, REQUEST_WINDOW_S)
    try:
        used = cache.incr(key)
    except ValueError:
        # The key expired between add() and incr(). One free request is a fair
        # trade for not needing a lock here.
        return
    if used > REQUEST_LIMIT:
        raise Conflict("Too many friend requests just now. Try again later.")


def _resolve_target(*, username: str | None, friend_code: str | None):
    """Find the account a request is aimed at, or None.

    Exact match only, on purpose: prefix search over usernames turns the
    instance into a browsable directory. Callers must treat None as "no
    result" without saying so - see `send_request`.
    """
    if friend_code:
        return User.objects.filter(friend_code=friend_code.strip().upper()).first()
    if username:
        return User.objects.filter(
            username__iexact=username.strip(), discoverable_by_username=True
        ).first()
    return None


def send_request(actor, *, username: str | None = None, friend_code: str | None = None):
    """Ask to be someone's friend. Returns the edge, or None if nothing happened.

    None covers "no such user", "they have username discovery off" and "they
    blocked you" identically, and the API layer answers 202 to all of them.
    Distinguishing them would make this endpoint a username oracle: anyone
    could confirm who holds an account on the instance by watching which
    guesses come back differently.

    Sending to someone who already asked you accepts instead - the
    `IntegrityError` branch is the same rule when the two arrive at once.
    """
    _rate_limit(actor)

    target = _resolve_target(username=username, friend_code=friend_code)
    if target is None:
        return None
    if target.pk == actor.pk:
        # Not an oracle: the caller already knows their own account exists.
        raise Conflict("You cannot add yourself.")

    low, high = ordered_pair(actor, target)
    existing = Friendship.objects.filter(user_low=low, user_high=high).first()
    if existing is not None:
        return _reconcile(existing, actor)

    try:
        with transaction.atomic():
            edge = Friendship.objects.create(
                user_low=low, user_high=high, requested_by=actor, status=Status.PENDING
            )
    except IntegrityError:
        # They asked at the same moment we did. Their row won the unique
        # constraint; applying the mutual-request rule to it gives both sides
        # the same outcome regardless of which insert landed first.
        edge = Friendship.objects.get(user_low=low, user_high=high)
        return _reconcile(edge, actor)

    record_event(verb="social.friend.requested", actor=actor, target=edge)
    return edge


def _reconcile(edge: Friendship, actor):
    """What sending a request means when an edge already exists."""
    if edge.status == Status.BLOCKED:
        return None
    if edge.status == Status.ACCEPTED:
        return edge
    if edge.requested_by_id == actor.pk:
        return edge  # already asked; asking twice is not an error
    return accept_request(actor, edge.pk)


def accept_request(user, friendship_id) -> Friendship:
    edge = _pending_for(user, friendship_id)
    if edge.requested_by_id == user.pk:
        raise Conflict("You sent this request; the other person accepts it.")

    edge.status = Status.ACCEPTED
    edge.responded_at = dj_timezone.now()
    edge.save(update_fields=["status", "responded_at", "updated_at"])
    record_event(verb="social.friend.accepted", actor=user, target=edge)
    return edge


def decline_request(user, friendship_id) -> None:
    """Delete the edge rather than marking it declined.

    A declined request that lingers means the same person can never ask again
    after a mistaken tap. Blocking is the tool for "never ask again", and it is
    the recipient's explicit choice.
    """
    edge = _pending_for(user, friendship_id)
    if edge.requested_by_id == user.pk:
        raise Conflict("You sent this request; cancel it instead.")
    edge.delete()
    record_event(
        verb="social.friend.declined",
        actor=user,
        target_type="social.friendship",
        target_id=friendship_id,
    )


def cancel_request(user, friendship_id) -> None:
    """Withdraw a request you sent."""
    edge = _pending_for(user, friendship_id)
    if edge.requested_by_id != user.pk:
        raise Conflict("You did not send this request; decline it instead.")
    edge.delete()


def _pending_for(user, friendship_id) -> Friendship:
    edge = Friendship.objects.filter(pk=friendship_id).first()
    # A stranger poking at request ids gets the same answer as one that does
    # not exist - the edge's existence is not theirs to learn.
    if edge is None or not edge.involves(user):
        raise NotFound("No such friend request.")
    if edge.status != Status.PENDING:
        raise Conflict("That request has already been answered.")
    return edge


# --------------------------------------------------------------------------
# Ending things
# --------------------------------------------------------------------------


def unfriend(user, other_id) -> None:
    """Remove the edge. Past entries stay exactly where they are.

    A workout you did together happened, and a friendship ending does not
    un-happen it. What stops is future partner logging.
    """
    other = _user_or_404(other_id)
    edge = get_friendship(user, other)
    if edge is None or edge.status != Status.ACCEPTED:
        raise NotFound("You are not friends with that user.")
    edge.delete()
    FriendPref.objects.filter(owner__in=[user, other], friend__in=[user, other]).delete()
    record_event(verb="social.friend.removed", actor=user, target=other)


def block(user, other_id) -> Friendship:
    """Stop all interaction, in both directions, from either side's request.

    Kept as a row rather than a deletion because a deleted edge is
    indistinguishable from never having met, and the blocker would start
    receiving requests again the next day.
    """
    other = _user_or_404(other_id)
    if other.pk == user.pk:
        raise Conflict("You cannot block yourself.")

    low, high = ordered_pair(user, other)
    edge, _ = Friendship.objects.get_or_create(
        user_low=low,
        user_high=high,
        defaults={"requested_by": user, "status": Status.BLOCKED},
    )
    edge.status = Status.BLOCKED
    edge.blocked_by = user
    edge.responded_at = dj_timezone.now()
    edge.save(update_fields=["status", "blocked_by", "responded_at", "updated_at"])
    FriendPref.objects.filter(owner__in=[user, other], friend__in=[user, other]).delete()
    record_event(verb="social.friend.blocked", actor=user, target=other)
    return edge


def unblock(user, other_id) -> None:
    other = _user_or_404(other_id)
    edge = get_friendship(user, other)
    if edge is None or edge.status != Status.BLOCKED:
        raise NotFound("That user is not blocked.")
    if edge.blocked_by_id != user.pk:
        # The other side blocked this one. Saying so would tell the blocked
        # user they were blocked, which is the one thing blocking should not
        # announce.
        raise NotFound("That user is not blocked.")
    edge.delete()


def _user_or_404(user_id):
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise NotFound("No such user.")
    return user


# --------------------------------------------------------------------------
# Per-friend preferences
# --------------------------------------------------------------------------


def get_prefs(owner, friend) -> FriendPref | None:
    return FriendPref.objects.filter(owner=owner, friend=friend).first()


def set_prefs(owner, friend_id, *, workout_partner: bool) -> FriendPref:
    """Update `owner`'s own settings about a friend.

    Requires an accepted friendship: a preference about someone you are not
    friends with has nothing to apply to, and silently storing one would let
    the table accumulate rows for strangers.
    """
    friend = _user_or_404(friend_id)
    if not are_friends(owner, friend):
        raise NotFound("You are not friends with that user.")

    pref, _ = FriendPref.objects.get_or_create(owner=owner, friend=friend)
    pref.workout_partner = workout_partner
    pref.save(update_fields=["workout_partner", "updated_at"])
    return pref


def workout_partners(user):
    """The friends `user` has ticked for the workout picker, as User rows.

    Presentation only. A friend missing from this list can still log a shared
    workout to `user`'s account - see `assert_can_log_for`, which deliberately
    does not consult it.
    """
    friends = friends_of(user)
    picked = set(
        FriendPref.objects.filter(owner=user, friend__in=friends, workout_partner=True).values_list(
            "friend_id", flat=True
        )
    )
    return [f for f in friends if f.pk in picked]


# --------------------------------------------------------------------------
# The one cross-user capability
# --------------------------------------------------------------------------


def assert_can_log_for(actor, user_ids) -> list:
    """The users `actor` may write a shared workout to, or raise.

    Raises rather than filtering. A silently dropped participant shows the
    person a ticked name next to someone whose log never received the entry,
    which is worse than an error they can act on.

    Deliberately ignores `FriendPref.workout_partner`: that is `actor`'s own
    display setting, and the subject's consent is the accepted friendship plus
    their `allow_partner_logging`.
    """
    wanted = list(dict.fromkeys(user_ids))  # de-duplicate, keep order
    if not wanted:
        return []

    found = {u.pk: u for u in User.objects.filter(pk__in=wanted)}
    resolved = []
    for user_id in wanted:
        subject = found.get(user_id)
        if subject is None or subject.pk == actor.pk:
            raise Conflict("That is not one of your friends.")
        if not are_friends(actor, subject):
            raise Conflict(f"You are not friends with {subject.username}.")
        if not subject.allow_partner_logging:
            raise Conflict(f"{subject.username} does not accept shared workouts.")
        resolved.append(subject)
    return resolved
