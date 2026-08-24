"""The friend graph.

Two tables, because three concerns turn up in one feature and only two of them
share a shape:

  * **`Friendship`** - *are A and B friends?* An edge has no owner, so it is
    one symmetric row per pair.
  * **`FriendPref`** - *what do I want from this friend?* A preference does
    have an owner, so it is directional: up to two rows per pair, one per side.

See `docs/roadmap-social.md` decisions 1-2 for why `workout_partner` lives on
the second table rather than being a boolean on the first, and for why it is a
presentation setting rather than a permission.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel

#: Unambiguous in handwriting and over a phone call: no 0/O, 1/I/L, 2/Z, 5/S,
#: 8/B. A friend code is read aloud in a gym far more often than it is pasted.
CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"

#: 10 characters of a 25-symbol alphabet is ~46 bits. Not a secret - knowing a
#: code only lets you *ask* to be someone's friend - but wide enough that the
#: instance cannot be walked by guessing, which is the actual attack.
CODE_LENGTH = 10


def generate_friend_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class Status(models.TextChoices):
    PENDING = "pending", "Request sent, awaiting a reply"
    ACCEPTED = "accepted", "Friends"
    BLOCKED = "blocked", "Blocked"


class FriendshipQuerySet(models.QuerySet):
    def involving(self, user) -> FriendshipQuerySet:
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(Q(user_low=user) | Q(user_high=user))

    def accepted(self) -> FriendshipQuerySet:
        return self.filter(status=Status.ACCEPTED)

    def pending(self) -> FriendshipQuerySet:
        return self.filter(status=Status.PENDING)


class Friendship(BaseModel):
    """One row per pair of users, in a canonical order.

    `user_low`/`user_high` are the two users sorted by primary key, enforced by
    a check constraint, and unique together. That earns its keep twice.

    "Are A and B friends" becomes one indexed lookup instead of
    ``Q(a=x, b=y) | Q(a=y, b=x)`` - the question every partner-logged workout
    starts with.

    And A requesting B at the same instant B requests A cannot produce two
    rows: the unique constraint turns the race into an `IntegrityError` that
    `services.send_request` catches and resolves as *mutual request implies
    accepted*. A `(from_user, to_user)` table cannot express that invariant
    without application-level locking.

    `on_delete=CASCADE`, unlike `OwnedModel`'s `SET_NULL`: a friendship with a
    deleted half is not a friendship.
    """

    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_low",
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_high",
    )
    #: Which side asked. The pair columns are ordered by UUID and so carry no
    #: direction at all; without this, "incoming" and "outgoing" requests are
    #: indistinguishable.
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friend_requests_sent",
    )
    status = models.CharField(max_length=16, choices=Status, default=Status.PENDING)
    #: Set only while `status` is BLOCKED. One side blocking is enough to stop
    #: every interaction, so this records who, for the unblock check.
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="friendships_blocked",
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    objects = FriendshipQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_low", "user_high"], name="social_friendship_pair"
            ),
            models.CheckConstraint(
                condition=Q(user_low__lt=F("user_high")),
                name="social_friendship_ordered",
            ),
        ]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return f"{self.user_low_id} <-> {self.user_high_id} ({self.status})"

    def other_than(self, user):
        """The far side of this edge, from `user`'s point of view."""
        return self.user_high if self.user_low_id == user.pk else self.user_low

    def involves(self, user) -> bool:
        return user.pk in (self.user_low_id, self.user_high_id)


class FriendPref(BaseModel):
    """`owner`'s settings about `friend`. Directional, and private to `owner`.

    Today this holds one field. Putting `workout_partner` on `Friendship`
    instead would look identical right now and stop looking identical at the
    second preference ("mute their timeline"), which would then mean migrating
    live data out of a row two people share. See `docs/roadmap-social.md`.

    Rows are created lazily on first write: a friend nobody has configured has
    no row, and `workout_partner=False` is the correct default for someone who
    was never pinned.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friend_prefs",
    )
    friend = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friend_prefs_about",
    )
    #: Whether `friend` appears in `owner`'s workout-player picker. Presentation
    #: only - it neither grants nor revokes anyone's ability to log a workout to
    #: `owner`'s account. That is the accepted friendship plus the subject's own
    #: `allow_partner_logging`.
    workout_partner = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "friend"], name="social_friendpref_pair"),
        ]

    def __str__(self) -> str:
        return f"{self.owner_id} -> {self.friend_id}"
