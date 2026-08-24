"""The friend graph.

The properties worth pinning here are the ones a plausible-looking
reimplementation gets wrong: that the pair table cannot hold two rows for one
pair, that a simultaneous mutual request converges instead of deadlocking, that
`workout_partner` is a display setting and not a permission, and that the
lookup endpoints do not tell a stranger who holds an account on the instance.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.core.exceptions import Conflict, NotFound
from apps.social import services
from apps.social.models import FriendPref, Friendship, Status

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    return User.objects.create_user(username="alex", password=PASSWORD)


@pytest.fixture
def blake(db):
    return User.objects.create_user(username="blake", password=PASSWORD)


@pytest.fixture
def casey(db):
    return User.objects.create_user(username="casey", password=PASSWORD)


def befriend(a, b) -> Friendship:
    services.send_request(a, username=b.username)
    edge = services.get_friendship(a, b)
    return services.accept_request(b, edge.pk)


# --------------------------------------------------------------------------
# The pair table
# --------------------------------------------------------------------------


def test_the_pair_is_stored_in_one_canonical_order(alex, blake):
    services.send_request(alex, username=blake.username)

    edge = Friendship.objects.get()
    assert edge.user_low_id < edge.user_high_id
    # Both users find the same row, from either direction.
    assert services.get_friendship(alex, blake) == edge
    assert services.get_friendship(blake, alex) == edge


def test_a_second_row_for_the_same_pair_is_rejected_by_the_database(alex, blake):
    services.send_request(alex, username=blake.username)
    low, high = services.ordered_pair(alex, blake)

    with pytest.raises(IntegrityError), transaction.atomic():
        Friendship.objects.create(user_low=low, user_high=high, requested_by=blake)


def test_an_out_of_order_pair_is_rejected_by_the_database(alex, blake):
    low, high = services.ordered_pair(alex, blake)

    with pytest.raises(IntegrityError), transaction.atomic():
        # user_low > user_high: the check constraint, not the application, is
        # what makes the canonical order safe to rely on.
        Friendship.objects.create(user_low=high, user_high=low, requested_by=alex)


def test_asking_someone_who_already_asked_you_accepts_instead(alex, blake):
    services.send_request(blake, username=alex.username)

    services.send_request(alex, username=blake.username)

    assert Friendship.objects.count() == 1
    assert services.are_friends(alex, blake)


def test_asking_twice_is_not_an_error_and_does_not_duplicate(alex, blake):
    first = services.send_request(alex, username=blake.username)
    second = services.send_request(alex, username=blake.username)

    assert first == second
    assert Friendship.objects.count() == 1
    assert second.status == Status.PENDING


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


def test_accepting_makes_both_sides_friends(alex, blake):
    befriend(alex, blake)

    assert services.are_friends(alex, blake)
    assert services.are_friends(blake, alex)
    assert list(services.friends_of(alex)) == [blake]
    assert list(services.friends_of(blake)) == [alex]


def test_a_pending_request_is_not_a_friendship(alex, blake):
    services.send_request(alex, username=blake.username)

    assert not services.are_friends(alex, blake)
    assert list(services.friends_of(alex)) == []


def test_the_sender_cannot_accept_their_own_request(alex, blake):
    edge = services.send_request(alex, username=blake.username)

    with pytest.raises(Conflict):
        services.accept_request(alex, edge.pk)


def test_declining_deletes_the_edge_so_they_can_ask_again(alex, blake):
    edge = services.send_request(alex, username=blake.username)

    services.decline_request(blake, edge.pk)

    assert Friendship.objects.count() == 0
    assert services.send_request(alex, username=blake.username) is not None


def test_a_stranger_cannot_answer_someone_elses_request(alex, blake, casey):
    edge = services.send_request(alex, username=blake.username)

    # 404, not 403: whether that id exists is not casey's to learn.
    with pytest.raises(NotFound):
        services.accept_request(casey, edge.pk)


def test_you_cannot_add_yourself(alex):
    with pytest.raises(Conflict):
        services.send_request(alex, username=alex.username)


# --------------------------------------------------------------------------
# Discovery must not become an oracle
# --------------------------------------------------------------------------


def test_an_unknown_username_looks_exactly_like_an_undiscoverable_one(alex, blake):
    blake.discoverable_by_username = False
    blake.save(update_fields=["discoverable_by_username"])

    assert services.send_request(alex, username="nobody-here") is None
    assert services.send_request(alex, username=blake.username) is None
    assert Friendship.objects.count() == 0


def test_a_friend_code_reaches_someone_who_is_not_discoverable_by_username(alex, blake):
    blake.discoverable_by_username = False
    blake.save(update_fields=["discoverable_by_username"])
    code = services.ensure_friend_code(blake)

    edge = services.send_request(alex, friend_code=code.lower())

    assert edge is not None
    assert edge.status == Status.PENDING


def test_rotating_a_friend_code_invalidates_the_old_one(alex, blake):
    old = services.ensure_friend_code(blake)
    new = services.rotate_friend_code(blake)

    assert old != new
    assert services.send_request(alex, friend_code=old) is None
    assert services.send_request(alex, friend_code=new) is not None


def test_friend_requests_are_rate_limited(alex, db):
    for n in range(services.REQUEST_LIMIT):
        User.objects.create_user(username=f"friend{n}", password=PASSWORD)
        services.send_request(alex, username=f"friend{n}")

    with pytest.raises(Conflict):
        services.send_request(alex, username="friend0")


# --------------------------------------------------------------------------
# Blocking, enforced once in the graph
# --------------------------------------------------------------------------


def test_blocking_stops_further_requests_without_announcing_itself(alex, blake):
    services.block(blake, alex.pk)

    # None, not an error: an error that only appears for blocked users tells
    # them they were blocked.
    assert services.send_request(alex, username=blake.username) is None
    assert not services.are_friends(alex, blake)


def test_blocking_ends_an_existing_friendship(alex, blake):
    befriend(alex, blake)

    services.block(blake, alex.pk)

    assert not services.are_friends(alex, blake)


def test_the_blocked_user_cannot_unblock_themselves(alex, blake):
    services.block(blake, alex.pk)

    with pytest.raises(NotFound):
        services.unblock(alex, blake.pk)

    assert services.get_friendship(alex, blake).status == Status.BLOCKED


def test_unfriending_leaves_the_pair_free_to_start_over(alex, blake):
    befriend(alex, blake)

    services.unfriend(alex, blake.pk)

    assert Friendship.objects.count() == 0
    assert services.send_request(alex, username=blake.username) is not None


# --------------------------------------------------------------------------
# Preferences are directional, and are not permissions
# --------------------------------------------------------------------------


def test_pinning_a_friend_is_one_sided(alex, blake):
    befriend(alex, blake)

    services.set_prefs(alex, blake.pk, workout_partner=True)

    assert services.workout_partners(alex) == [blake]
    # blake pinned nobody; alex's choice is not blake's.
    assert services.workout_partners(blake) == []


def test_an_unpinned_friend_may_still_log_a_shared_workout(alex, blake):
    """`workout_partner` is presentation, not permission.

    If this ever starts raising, the Settings checkbox has quietly become a
    privacy control that its own UI copy says it is not.
    """
    befriend(alex, blake)
    assert services.workout_partners(alex) == []

    assert services.assert_can_log_for(blake, [alex.pk]) == [alex]


def test_preferences_cannot_be_set_for_a_non_friend(alex, blake):
    with pytest.raises(NotFound):
        services.set_prefs(alex, blake.pk, workout_partner=True)


def test_unfriending_clears_both_sides_preferences(alex, blake):
    befriend(alex, blake)
    services.set_prefs(alex, blake.pk, workout_partner=True)
    services.set_prefs(blake, alex.pk, workout_partner=True)

    services.unfriend(alex, blake.pk)

    assert FriendPref.objects.count() == 0


# --------------------------------------------------------------------------
# The one cross-user capability
# --------------------------------------------------------------------------


def test_a_non_friend_is_refused_rather_than_skipped(alex, blake, casey):
    befriend(alex, blake)

    # A dropped participant would show a ticked name next to someone whose log
    # never received the entry.
    with pytest.raises(Conflict):
        services.assert_can_log_for(alex, [blake.pk, casey.pk])


def test_a_pending_friend_cannot_be_logged_for(alex, blake):
    services.send_request(alex, username=blake.username)

    with pytest.raises(Conflict):
        services.assert_can_log_for(alex, [blake.pk])


def test_opting_out_of_partner_logging_is_a_real_refusal(alex, blake):
    befriend(alex, blake)
    blake.allow_partner_logging = False
    blake.save(update_fields=["allow_partner_logging"])

    with pytest.raises(Conflict):
        services.assert_can_log_for(alex, [blake.pk])


def test_duplicate_partner_ids_resolve_once(alex, blake):
    befriend(alex, blake)

    assert services.assert_can_log_for(alex, [blake.pk, blake.pk]) == [blake]


def test_no_partners_is_not_an_error(alex):
    assert services.assert_can_log_for(alex, []) == []
