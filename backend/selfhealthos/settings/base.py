"""Settings shared by every environment.

Values come from the environment. Compose enforces the genuinely required ones
with `${VAR:?}`, so the defaults here exist only to keep `manage.py` and the
Docker build usable without a full .env.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, "insecure-default-override-me"),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
    DJANGO_LOG_LEVEL=(str, "INFO"),
    DJANGO_TIME_ZONE=(str, "UTC"),
    DATABASE_URL=(str, "postgresql://selfhealthos:selfhealthos@db:5432/selfhealthos"),
    REDIS_URL=(str, "redis://redis:6379/0"),
    SITE_URL=(str, "http://localhost"),
)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")

#: Always allowed, on top of whatever the operator sets. These are internal
#: compose-network hostnames, not public addresses - they're fixed by
#: compose.yaml's service names, not something an operator's own
#: DJANGO_ALLOWED_HOSTS should need to know about:
#:   - "django": frontend/src/lib/api/server.ts's serverGet() fetches
#:     http://django:8000 directly from Next's server components (every
#:     server-rendered page), bypassing next.config.ts's rewrite proxy
#:     entirely since it's a server-to-server call, not a proxied browser
#:     request - so the Host header it sends is literally "django:8000".
#:   - "127.0.0.1": Docker's own healthcheck for this container calls itself
#:     over loopback (see compose.yaml). Without this, the healthcheck can
#:     never pass, which cascades into `next` never starting at all.
INTERNAL_HOSTS = ["django", "127.0.0.1"]

_configured_hosts = env("DJANGO_ALLOWED_HOSTS")
ALLOWED_HOSTS = _configured_hosts + [h for h in INTERNAL_HOSTS if h not in _configured_hosts]
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")
SITE_URL = env("SITE_URL")

# --- Applications --------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.tokens",
    "apps.api",
    "apps.health",
    "apps.fitness",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "selfhealthos.urls"
WSGI_APPLICATION = "selfhealthos.wsgi.application"
ASGI_APPLICATION = "selfhealthos.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ------------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# UUIDv7 primary keys are declared explicitly on apps.core.BaseModel; this only
# covers Django's own tables.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

# Deliberately empty. This is a self-hosted app and the account belongs to
# whoever is installing it - "admin"/"admin" must be allowed if that's what
# the operator wants. Do not add validators back in.
AUTH_PASSWORD_VALIDATORS = []

# --- Internationalisation ------------------------------------------------

LANGUAGE_CODE = "en-us"
# Everything is stored in UTC; per-user display timezones live on the account.
TIME_ZONE = env("DJANGO_TIME_ZONE")
USE_I18N = True
USE_TZ = True

# --- Static and media ----------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- Reverse proxy ---------------------------------------------------------
# selfhealthos ships with no bundled reverse proxy. If you front it with one
# (nginx, Traefik, a tunnel) for TLS, these let Django trust its forwarded
# headers; if you don't, they're harmless no-ops.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_NAME = "selfhealthos_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_NAME = "selfhealthos_csrftoken"
CSRF_COOKIE_HTTPONLY = False  # the frontend must read it to echo X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"

# --- Celery --------------------------------------------------------------

REDIS_URL = env("REDIS_URL")

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# --- Wearable connections -------------------------------------------------

# Encrypts provider client secrets and OAuth tokens at rest. Falls back to the
# signing key so the feature works without another required variable - with
# the consequence that rotating DJANGO_SECRET_KEY makes stored credentials
# unreadable and every connection has to be re-authorised. Set this separately
# if the signing key is ever going to be rotated on its own.
CREDENTIAL_ENCRYPTION_KEY = env("CREDENTIAL_ENCRYPTION_KEY", default="")

# Where Fitbit sends the browser back to. Must match a Redirect URL registered
# at dev.fitbit.com *exactly*, including scheme and any trailing slash. Fitbit
# never resolves this itself - it only ever sends a 302 to the browser - which
# is why this can point anywhere reachable by the operator's own browser, not
# necessarily a public hostname.
FITBIT_REDIRECT_URI = env("FITBIT_REDIRECT_URI", default=f"{SITE_URL}/fitbit/callback")

# --- Logging -------------------------------------------------------------

LOG_LEVEL = env("DJANGO_LOG_LEVEL")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "{levelname:<8} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "selfhealthos": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
        "apps": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
        "mcp_server": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
    },
}
