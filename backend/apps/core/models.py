"""Foundational model plumbing every app builds on."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from uuid6 import uuid7


class BaseModel(models.Model):
    """UUIDv7 primary key plus creation/update timestamps.

    UUIDv7 rather than v4: it is time-ordered, so it indexes and paginates like
    a sequential integer while still being safe to expose in URLs and MCP
    output. Sequential integers are never exposed anywhere in this project.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        get_latest_by = "created_at"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.pk}>"


class Visibility(models.TextChoices):
    SHARED = "shared", "Shared with everyone"
    PRIVATE = "private", "Only the owner"


class OwnedQuerySet(models.QuerySet):
    def visible_to(self, user) -> "OwnedQuerySet":
        """Rows `user` may read *from the shared library*.

        SHARED here means "shared with everyone signed in to this instance" -
        it is the household-library model, and it predates the friend graph in
        `apps.social`. It is deliberately not friend-aware: health rows are
        read through `DeviceEntryQuerySet.for_user()`, which filters on
        `created_by`, and the friend graph grants exactly one cross-user
        capability - writing a shared workout - and no reads at all.

        The deferred timeline brings its own three-value audience
        (private/friends/public) stamped on each shared item rather than
        retrofitting one here; see `docs/roadmap-social.md`. Read this filter
        as "the library everyone on this instance can see", not as the
        instance's whole privacy model.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(Q(visibility=Visibility.SHARED) | Q(created_by=user))

    def owned_by(self, user) -> "OwnedQuerySet":
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(created_by=user)

    def shared(self) -> "OwnedQuerySet":
        """Rows visible to a caller with no user identity.

        Used by MCP, which has no session until access tokens land in M3. It
        sees the shared library and can never reach a row marked private, which
        is the safe default for a caller we cannot attribute to a person.
        """
        return self.filter(visibility=Visibility.SHARED)


class OwnedModel(BaseModel):
    """Attribution without isolation.

    `created_by` answers "who added this" for the audit trail and the "mine"
    filter; it is not a permission boundary.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        # Deleting a user must not delete the household's shared library.
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
    )
    visibility = models.CharField(
        max_length=16,
        choices=Visibility,
        default=Visibility.SHARED,
        db_index=True,
    )

    objects = OwnedQuerySet.as_manager()

    class Meta:
        abstract = True


class Tag(BaseModel):
    """One vocabulary across the whole portal.

    Deliberately not per-app: a "solar" tag should mean the same thing on a
    YouTube summary, a saved document and a property listing.
    """

    class Kind(models.TextChoices):
        MANUAL = "manual", "Added by a person"
        AUTO = "auto", "Extracted by a model"

    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=64, unique=True)
    kind = models.CharField(max_length=16, choices=Kind, default=Kind.MANUAL)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["kind"])]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_or_create_for_name(cls, name: str, *, kind: str = Kind.MANUAL) -> "Tag":
        """Resolve a free-text topic to a tag, matching on slug not casing."""
        name = " ".join(name.split())[:64]
        slug = slugify(name)[:64]
        if not slug:
            raise ValueError(f"tag name produces an empty slug: {name!r}")
        tag, created = cls.objects.get_or_create(slug=slug, defaults={"name": name, "kind": kind})
        # A tag first seen from a model but later applied by hand is a real tag.
        if not created and tag.kind == cls.Kind.AUTO and kind == cls.Kind.MANUAL:
            tag.kind = cls.Kind.MANUAL
            tag.save(update_fields=["kind", "updated_at"])
        return tag


class Taggable(models.Model):
    """Mixin giving a concrete model its own M2M through-table to Tag.

    An explicit per-model M2M rather than a GenericForeignKey: real foreign
    keys, real indexes, and joins the query planner understands.
    """

    tags = models.ManyToManyField(Tag, blank=True, related_name="%(app_label)s_%(class)s_set")

    class Meta:
        abstract = True


class Event(models.Model):
    """Append-only audit log.

    The user's model is "anyone logged in can see everything, but log who did
    what" - this table is the second half of that sentence.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    verb = models.CharField(max_length=64, db_index=True)  # e.g. "video.summarised"
    target_type = models.CharField(max_length=64, blank=True)  # e.g. "youtube.video"
    target_id = models.UUIDField(null=True, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["verb", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.verb} by {self.actor_id or 'system'}"

    def save(self, *args, **kwargs):
        # Append-only: an audit trail that can be edited is not an audit trail.
        if not self._state.adding:
            raise ValueError("Event rows are immutable")
        super().save(*args, **kwargs)
