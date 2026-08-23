from .base import *  # noqa: F403
from .base import env

DEBUG = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Only turn this on if you're not already redirecting at a reverse proxy in
# front of Django - doing it in both places loops.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

if SECRET_KEY == "insecure-default-override-me":  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production")
