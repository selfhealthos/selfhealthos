"""Settings used only by `collectstatic` during the Docker image build.

The build has no database, no Redis and no real secret, so this exists purely
so static collection cannot depend on runtime configuration.
"""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "build-only-not-a-secret"
