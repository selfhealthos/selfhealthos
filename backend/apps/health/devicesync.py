"""Merging rows that originated on a phone.

One function, called by both the `one-data` importer and the phone sync
endpoint. They implement the same rule, and the failure mode of two copies of
it is not a crash but a quiet divergence: an entry that the importer would
have kept and the endpoint overwrites, discovered weeks later as a gap in a
chart. Keeping it in one place is the only way to test it once.

The rule, in full:

  * **`client_id` is identity.** The UUID the phone generated when the row was
    first saved, offline, possibly days before the server heard about it. The
    same entry arriving twice - a retried request, a second phone, a re-run
    import - is one row. This is what makes the protocol safe to replay, which
    in turn is what lets the phone resend anything it is unsure about rather
    than having to decide.

  * **`client_updated_at` breaks ties.** Higher wins. It is the only conflict
    rule available without a coordinator, and it is why the phone must send its
    own `updatedAt` rather than letting the server stamp arrival time: two
    entries can arrive in the opposite order to the one they were edited in.

  * **A tombstone is an update, not a delete.** `deleted_at` is set and the row
    stays. A hard delete would resurrect the entry on the next sync from a
    phone that still has it, which is the bug the column exists to prevent.
"""

from __future__ import annotations

from enum import StrEnum

from django.db import IntegrityError, transaction
from django.utils import timezone


class Outcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    #: Accepted, but nothing written - what the server holds is at least as new.
    UNCHANGED = "unchanged"
    DELETED = "deleted"


class Rejected(Exception):
    """This row cannot be stored, and the caller must be told which one.

    Raised rather than returned so a caller cannot forget to check. The sync
    endpoint turns it into a per-row rejection; the batch still succeeds,
    because one malformed entry must not strand the other forty.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _write(fn) -> None:
    """Run one write in its own savepoint, turning a constraint clash into a
    named rejection instead of a request-wide 500.

    A handful of models carry a uniqueness rule beyond `client_id` - `OfficeDay`
    is one row per day, for instance, so two phone rows naming the same date
    collide. Uncaught, `IntegrityError` doesn't just fail that row: it poisons
    whatever transaction wraps the request, so every row after it in the same
    batch fails too, and the phone gets a 500 instead of a reply naming the
    one bad row. The savepoint keeps the damage local to this write so the
    rest of the batch still commits.
    """
    try:
        with transaction.atomic():
            fn()
    except IntegrityError as exc:
        raise Rejected("conflicts with an existing record") from exc


def merge(
    model,
    *,
    user,
    client_id,
    client_updated_at=None,
    defaults: dict | None = None,
    deleted: bool = False,
    natural_key: dict | None = None,
) -> Outcome:
    """Store one device row, idempotently. Returns what happened to it.

    `natural_key` is for models with a uniqueness rule beyond `client_id` -
    `OfficeDay` is one row per day, for instance (see the module docstring on
    `_write`). A phone that tombstones a row and mints a fresh id for the same
    natural key - toggling a day off and back on before the delete has synced
    is exactly this - would otherwise collide forever: the old row keeps
    occupying the slot, the new id never matches it by `client_id`, and every
    retry fails the same `IntegrityError`. When a `client_id` lookup finds
    nothing, falling back to the natural key adopts that row instead of
    fighting it, and the same `client_updated_at` tie-break decides whether
    the incoming write actually changes anything.
    """
    if not client_id:
        raise Rejected("missing client id")

    defaults = dict(defaults or {})
    # Ownership is decided here, never by the payload: a phone that could name
    # `created_by` could file entries against another member of the household.
    defaults.pop("created_by", None)

    existing = model.objects.filter(client_id=client_id).first()

    if existing is not None and existing.created_by_id != getattr(user, "pk", None):
        # `client_id` is unique across the whole table, not per user, so
        # without this check presenting someone else's id would overwrite their
        # entry. There is no second row this could become - the constraint
        # forbids it - so the only honest answer is to refuse this one.
        raise Rejected("client id belongs to another account")

    if existing is None and natural_key:
        existing = model.objects.filter(created_by=user, **natural_key).first()

    if existing is None:
        if deleted:
            # Created and deleted on the phone before it ever reached the
            # server. Nothing to tombstone, and writing one would invent a row
            # the server never held. Accepted, so the phone stops resending.
            return Outcome.UNCHANGED
        _write(
            lambda: model.objects.create(
                client_id=client_id,
                client_updated_at=client_updated_at,
                created_by=user,
                **defaults,
            )
        )
        return Outcome.CREATED

    if (
        client_updated_at
        and existing.client_updated_at
        and existing.client_updated_at >= client_updated_at
    ):
        return Outcome.UNCHANGED

    if deleted:
        # Idempotent: a tombstone that arrives twice must not move the deletion
        # time, or "when did I delete this" becomes "when did the phone last
        # retry".
        if existing.deleted_at is None:
            existing.deleted_at = timezone.now()
        existing.client_id = client_id
        existing.client_updated_at = client_updated_at
        existing.save()
        return Outcome.DELETED

    for key, value in defaults.items():
        setattr(existing, key, value)
    # Only ever moves when `existing` was adopted via `natural_key` above - a
    # match found by `client_id` already has this value. The adopted row's
    # identity has to move to the id the phone is now using, or the next sync
    # of the same id looks like a brand new row and reopens the same natural
    # key collision this fallback exists to close.
    existing.client_id = client_id
    existing.client_updated_at = client_updated_at
    # An edit newer than the delete wins. That is the same last-write-wins rule
    # the timestamps already encode, applied to the tombstone rather than to a
    # column, and it is what lets an accidental delete be undone by re-saving.
    existing.deleted_at = None
    _write(existing.save)
    return Outcome.UPDATED
