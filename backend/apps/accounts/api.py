"""Session authentication for the browser, plus self-serve signup.

The Next.js frontend proxies /api/* to this service (see frontend/next.config.ts),
putting the frontend and the API on one origin so the session cookie is
first-party. That means no tokens in localStorage, no CORS layer, and no
refresh dance - at the cost of needing a CSRF token on unsafe methods.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.middleware.csrf import get_token
from ninja import File, Router, Schema, Status
from ninja.files import UploadedFile

from apps.core.exceptions import DomainError
from apps.core.services import record_event

from . import services
from .models import User

router = Router(tags=["auth"])


class LoginIn(Schema):
    username: str
    password: str


class SignupIn(Schema):
    username: str
    password: str
    birth_date: datetime.date
    sex: str = ""


class UserOut(Schema):
    id: str
    username: str
    first_name: str = ""
    last_name: str = ""
    birth_date: datetime.date | None = None
    sex: str = ""
    avatar_url: str | None = None
    timezone: str = "UTC"
    is_staff: bool = False


class AccountProfileIn(Schema):
    """Every field optional - see `services.update_profile` on why PATCH."""

    timezone: str | None = None


class AccountTimezonesOut(Schema):
    """The picker's options, plus what the caller is currently set to.

    `current` rides along so the page can select the right option without a
    second request, and so a zone outside `timezones` (a legacy alias set by
    an API client) is still shown rather than silently reading as unset.
    """

    timezones: list[str]
    current: str


class CsrfOut(Schema):
    csrf_token: str


class InvalidCredentials(DomainError):
    status_code = 401
    title = "Sign in failed"


class UsernameTaken(DomainError):
    status_code = 409
    title = "Username already taken"


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.pk),
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        birth_date=user.birth_date,
        sex=user.sex,
        avatar_url=user.avatar.url if user.avatar else None,
        timezone=user.timezone,
        is_staff=user.is_staff,
    )


@router.get("/csrf", response=CsrfOut, auth=None, operation_id="getCsrfToken")
def csrf(request):
    """Fetch a CSRF token and set the cookie. Call before POSTing to /login or /signup."""
    return CsrfOut(csrf_token=get_token(request))


@router.post("/signup", response={201: UserOut}, auth=None, operation_id="signup")
def signup_view(request, payload: SignupIn):
    """Self-serve registration.

    No password complexity or length rules by design - this is a self-hosted
    app and the account belongs to whoever is installing it. `admin`/`admin`
    is a legitimate choice here, not a bug.
    """
    username = payload.username.strip()
    if not username:
        raise DomainError("Username is required.")
    if User.objects.filter(username__iexact=username).exists():
        raise UsernameTaken(f"The username {username!r} is already taken.")

    try:
        user = User.objects.create_user(
            username=username,
            password=payload.password,
            birth_date=payload.birth_date,
            sex=payload.sex,
        )
    except IntegrityError as exc:
        raise UsernameTaken(f"The username {username!r} is already taken.") from exc

    login(request, user)
    record_event(verb="user.signed_up", actor=user, target=user)
    return Status(201, _user_out(user))


@router.post("/login", response=UserOut, auth=None, operation_id="login")
def login_view(request, payload: LoginIn):
    user = authenticate(request, username=payload.username.strip(), password=payload.password)
    if user is None:
        # Deliberately identical whether the username is unknown or the
        # password is wrong - the difference tells an attacker who has an
        # account here.
        raise InvalidCredentials("That username and password combination was not recognised.")
    login(request, user)
    record_event(verb="user.logged_in", actor=user, target=user)
    return _user_out(user)


@router.post("/logout", response={204: None}, operation_id="logout")
def logout_view(request):
    record_event(verb="user.logged_out", actor=request.user, target=request.user)
    logout(request)
    return Status(204, None)


@router.get("/me", response=UserOut, operation_id="getCurrentUser")
def me(request):
    return _user_out(request.user)


@router.patch("/me", response=UserOut, operation_id="updateCurrentUser")
def update_me(request, payload: AccountProfileIn):
    """Edit your own account settings.

    Not scope-gated, matching `/me/avatar`: there is no `accounts:*` scope in
    `apps.tokens.scopes`, and inventing one here would grant it to nobody -
    none of the token presets carry it - while making the browser's own
    session the only caller that works. If account writes ever need to be
    delegable to a token, add the scope to the vocabulary first.
    """
    sent = payload.dict(exclude_unset=True)
    user = services.update_profile(request.auth, timezone=sent.get("timezone"), fields=sent.keys())
    return _user_out(user)


@router.get("/timezones", response=AccountTimezonesOut, operation_id="listTimezones")
def timezones(request):
    """The IANA zone list, read from this server's own tz database.

    Served rather than hardcoded in the frontend so the list the picker offers
    and the list `set_timezone` validates against can never disagree.
    """
    return AccountTimezonesOut(
        timezones=services.timezone_choices(),
        current=request.auth.timezone,
    )


@router.post("/me/avatar", response=UserOut, operation_id="uploadAvatar")
def upload_avatar(request, file: UploadedFile = File(...)):
    user = request.auth
    user.avatar = file
    user.save(update_fields=["avatar"])
    record_event(verb="user.avatar_updated", actor=user, target=user)
    return _user_out(user)
