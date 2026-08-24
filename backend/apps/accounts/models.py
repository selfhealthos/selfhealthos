"""Identity.

The custom user model exists from the very first migration deliberately:
swapping ``AUTH_USER_MODEL`` after any data exists is one of the few genuinely
painful migrations in Django.

Username/password only for now — no email or social login. `birth_date` and
`sex` are collected at signup and live here (not on health.Profile) because
they're account-level identity, not Health-specific settings; scoring.py
reads them off the user directly for its age/sex-personalised curves.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone as dj_timezone
from django.utils.translation import gettext_lazy as _
from uuid6 import uuid7


class Sex(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"
    OTHER = "other", "Other / prefer not to say"


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=16, choices=Sex, blank=True)
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", null=True, blank=True)

    # Display preferences. Storage is always UTC; this is presentation only.
    timezone = models.CharField(max_length=64, default="UTC")
    locale = models.CharField(max_length=16, default="en")

    # --- Social ----------------------------------------------------------
    #: Short, shareable, rotatable. Read aloud in a gym or pasted into a chat
    #: to add someone without the instance exposing a browsable user list -
    #: the alternative, prefix-searching usernames, is a scrape target. Null
    #: until first needed; `apps.social.services.ensure_friend_code` mints it.
    friend_code = models.CharField(max_length=16, unique=True, null=True, blank=True, default=None)
    #: Off means friend requests can only reach this account via `friend_code`.
    discoverable_by_username = models.BooleanField(default=True)
    #: Whether an accepted friend may log a shared workout to this account.
    #: This is the permission; a friend being ticked in someone's workout
    #: picker is not (see `apps.social.models.FriendPref.workout_partner`).
    allow_partner_logging = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username

    @property
    def age_years(self) -> int | None:
        """Whole years since birth_date, or None if unset.

        Feeds scoring.py's age-adjusted VO2max curve; unset simply means that
        curve falls back to its baseline rather than personalising.
        """
        if not self.birth_date:
            return None
        today = dj_timezone.localdate()
        years = today.year - self.birth_date.year
        had_birthday = (today.month, today.day) >= (self.birth_date.month, self.birth_date.day)
        return years if had_birthday else years - 1
