from .base import *  # noqa: F403
from .base import env  # noqa: F401

DEBUG = True

# Tolerant so a plain-HTTP setup (or `manage.py runserver`) doesn't silently
# drop the session cookie.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# WhiteNoise's manifest storage refuses to serve any file missing from
# staticfiles.json, which only exists after collectstatic. Dev never runs it.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

INTERNAL_IPS = ["127.0.0.1"]
