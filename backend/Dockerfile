# syntax=docker/dockerfile:1.7

# One image serves django, mcp and worker - they differ only in their command,
# which is what keeps the MCP tools and the REST API on the same service layer.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # The uv cache mount is on a different filesystem to site-packages, so
    # hardlinking always fails; copying is what actually happens either way.
    UV_LINK_MODE=copy
WORKDIR /app

# libpq5 for psycopg; nothing GIS-related - this project has no geo models.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv


FROM base AS deps
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r pyproject.toml


# --- dev: source is bind-mounted over /app by compose.dev.yaml -------------
FROM deps AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r pyproject.toml --extra dev
COPY . .
RUN mkdir -p /app/media /app/staticfiles
EXPOSE 8000 8080


# --- runner: self-contained production image ------------------------------
FROM deps AS runner
COPY . .
RUN DJANGO_SETTINGS_MODULE=selfhealthos.settings.build python manage.py collectstatic --noinput

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/media \
    && chown -R app:app /app/media /app/staticfiles
USER app

EXPOSE 8000 8080
