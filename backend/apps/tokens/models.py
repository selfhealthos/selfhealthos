"""Long-lived bearer tokens for clients that cannot hold a session.

The browser authenticates with a first-party session cookie, which works
because there is a login form and a cookie jar. Claude Code (via MCP) and any
script hitting the REST API directly have neither: they run unattended, with
nobody present to type a password.

Opaque and stored hashed, not a JWT. Revocation is the property that matters
most here - a token needs to be killable the moment it's no longer wanted -
and revoking a JWT means a server-side blocklist, which is a database lookup
per request, which is exactly what JWTs exist to avoid. They solve a
horizontal-scale problem one self-hosted instance does not have. An indexed
lookup on this table costs a fraction of a millisecond.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel

from . import scopes as scope_defs

#: Bytes of entropy in the secret half. 32 bytes is 256 bits: not guessable at
#: any rate, which is why the stored hash is a plain SHA-256 rather than a slow
#: KDF. Argon2 and bcrypt exist to make *low-entropy human passwords* expensive
#: to brute-force; against a random 256-bit string they buy nothing and cost a
#: derivation on every API call.
SECRET_BYTES = 32

#: Human-readable marker, so a token found in a config file is identifiable.
PREFIX = "shos_pat_"

#: Characters of the secret kept in the clear, for lookup and for showing
#: "shos_pat_a1b2c3d4…" in the UI next to a token's name.
LOOKUP_CHARS = 8

#: Idle lifetime. Slid forward on every use, so a client in regular use never
#: expires and never needs re-issuing. Six months of total silence is a
#: dead-credential cleanup, not a security control.
DEFAULT_TTL = timedelta(days=180)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class AccessTokenQuerySet(models.QuerySet):
    def live(self) -> AccessTokenQuerySet:
        now = timezone.now()
        return self.filter(revoked_at__isnull=True).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )

    def for_user(self, user) -> AccessTokenQuerySet:
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(user=user)


class AccessToken(BaseModel):
    """One credential, for one client, held by one person."""

    class Kind(models.TextChoices):
        DEVICE = "device", "Device (phone, tablet)"
        AGENT = "agent", "Agent (Claude Code / MCP)"
        SCRIPT = "script", "Script"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="access_tokens"
    )
    #: What holds it - "Pixel 8", "Claude Code (desktop)". Shown in the UI, so
    #: revoking the right one does not need guesswork.
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=16, choices=Kind, default=Kind.DEVICE)

    #: The clear prefix, indexed. Lookup narrows on this, then the full hash is
    #: compared in constant time - so authentication is one indexed row read
    #: rather than a scan hashing every candidate.
    lookup = models.CharField(max_length=16, unique=True, editable=False)
    token_hash = models.CharField(max_length=64, editable=False)

    scopes = models.JSONField(default=list)

    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = AccessTokenQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.masked})"

    # -- lifecycle -------------------------------------------------------

    @classmethod
    def issue(
        cls,
        *,
        user,
        name: str,
        scopes: list[str],
        kind: str = Kind.DEVICE,
        ttl: timedelta | None = DEFAULT_TTL,
    ) -> tuple[AccessToken, str]:
        """Create a token and return it with its secret.

        The secret is returned exactly once and never stored. If it is lost the
        answer is a new token, not a recovery path - a credential that can be
        read back out of the database is not much of a credential.
        """
        secret = secrets.token_urlsafe(SECRET_BYTES)
        full = f"{PREFIX}{secret}"
        token = cls.objects.create(
            user=user,
            name=name.strip()[:100] or "unnamed",
            kind=kind,
            lookup=secret[:LOOKUP_CHARS],
            token_hash=hash_secret(secret),
            scopes=scope_defs.normalise(scopes),
            expires_at=timezone.now() + ttl if ttl else None,
        )
        return token, full

    @classmethod
    def authenticate(cls, presented: str) -> AccessToken | None:
        """Resolve a bearer string to a live token, or None."""
        if not presented or not presented.startswith(PREFIX):
            return None
        secret = presented[len(PREFIX) :]
        if len(secret) < LOOKUP_CHARS:
            return None

        token = cls.objects.live().filter(lookup=secret[:LOOKUP_CHARS]).first()
        if token is None:
            return None
        # Constant-time: a timing difference here leaks the hash a byte at a
        # time to anyone who can measure it.
        if not secrets.compare_digest(token.token_hash, hash_secret(secret)):
            return None
        return token

    def touch(self, *, ip: str | None = None) -> None:
        """Record use and slide the expiry forward.

        Written with `update()` rather than `save()`: this runs on every
        authenticated request, and it must not race with a concurrent write to
        the same row or drag the whole model through a round trip.
        """
        now = timezone.now()
        fields: dict = {"last_used_at": now}
        if ip:
            fields["last_used_ip"] = ip
        if self.expires_at is not None:
            fields["expires_at"] = now + DEFAULT_TTL
        type(self).objects.filter(pk=self.pk).update(**fields)

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at", "updated_at"])

    # -- presentation ----------------------------------------------------

    @property
    def masked(self) -> str:
        return f"{PREFIX}{self.lookup}…"

    @property
    def is_live(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])
