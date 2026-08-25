# CLAUDE.md

Guidance for Claude Code (and future contributors) working in this repo.

## Layout

```
backend/    Django + django-ninja REST API, Celery workers, MCP server
frontend/   Next.js (App Router) UI
compose.yaml / compose.dev.yaml   Docker Compose, prod base + dev overlay
```

There is no bundled reverse proxy. The compose stack serves plain HTTP by default; an operator who wants public HTTPS fronts it with their own (Traefik, nginx, a tunnel) — see the docs site's self-hosting guide. This is also why the MCP endpoint works over plain `http://` out of the box: nothing here requires TLS.

`backend/apps/health/` is the core domain app — Health is the product, not one feature among several. Everything else (`accounts`, `tokens`, `core`, `api`) exists to support it.

## Local development

```bash
cp .env.example .env
docker compose up -d            # dev overlay applies automatically via COMPOSE_FILE in .env
docker compose exec django pytest
docker compose exec django ruff check --fix .
docker compose exec django ruff format .
```

After changing any backend API surface (new endpoint, changed schema), regenerate the frontend's types before touching frontend code:

```bash
# The API is mounted at /api/v1/, so the spec is there too - /api/openapi.json 404s.
# Django isn't published to the host by default; go through the frontend's port.
curl http://localhost/api/v1/openapi.json -o frontend/openapi.json
cd frontend && npm run generate:api && npm run typecheck
```

The frontend never hand-writes response shapes — `frontend/src/lib/api/schema.d.ts` is generated, not edited.

To run the MCP server standalone (outside compose) for local testing:

```bash
uvicorn mcp_server.app:app --host 127.0.0.1 --port 8080
claude mcp add --transport http selfhealthos http://127.0.0.1:8080/mcp \
  --header "Authorization: Bearer <a token from Settings>" --scope local
```

`app.py`'s DNS-rebinding protection only accepts requests whose `Host` header matches `DJANGO_ALLOWED_HOSTS` or the `INTERNAL_HOSTS` list in that file — connecting on a different host/port than `127.0.0.1:8080` needs a matching entry added there.

## Workflow: push as you go

**Commit and push after each feature actually works, not in one large batch at the end.** A feature here means a coherent, verified unit — a phase of a larger build, one bug fix, one new endpoint plus its frontend and tests. The point is revertability: if something two features back turns out to be wrong, `git revert`/`reset` to the commit before it should be possible without also losing unrelated work done since. Prefer several focused commits over one commit that bundles several unrelated changes, for the same reason.

**Before pushing any backend change, run `ruff check .` and `ruff format --check .` from `backend/` and fix everything they report.** This is not optional and not just "worth doing" — `ci.yml` runs both on every push to `main`, so skipping it locally just moves the failure to GitHub Actions instead of catching it before it's public. `docker compose exec django ruff check --fix . && docker compose exec django ruff format .` is the normal path; if the compose stack isn't up (Docker Desktop not running, no `.env` yet), fall back to `pip install ruff` and run `ruff check .` / `ruff format --check .` directly from `backend/` — either path catches the same formatting drift `ci.yml` enforces. The rest of what CI runs is worth running locally too where practical (`pytest`, `manage.py makemigrations --check --dry-run`, frontend `typecheck`/`build`) — pushing something CI immediately fails on isn't a real checkpoint.

**Update `selfhealthos.github.io` in the same body of work whenever user-facing behavior changes** — a new feature, a changed `.env` variable, a changed setup step — not as a follow-up later. Concretely: touch `docs/features/overview.md` (and the relevant feature page) if what shipped is user-visible, touch `docs/getting-started/installation.md` or `docs/getting-started/configuration.md` if `.env.example` or the compose file changed, and add a `blog/` entry (see that repo's own CLAUDE.md) once a batch of work amounts to a release worth telling users about — not necessarily every single commit. A merged feature whose docs update lands "later" is exactly the drift this convention exists to prevent.

## Architecture conventions

- **Services own the logic.** REST routers (`apps/*/api.py`), MCP tools (`mcp_server/tools/*.py`), and Celery tasks (`apps/*/tasks.py`) are all thin callers into a shared `apps/*/services.py`. Never put business logic directly in a router or a Celery task — if REST, MCP, and background jobs each reimplement the same rule, they *will* drift. If you're adding a new capability, add it to `services.py` first and call it from wherever needs it.
- **Response schema naming.** Every django-ninja response schema class must be prefixed per-app, e.g. `HealthSummaryOut`, not `SummaryOut`. OpenAPI's generated component map is keyed by class name only — an unprefixed name from one app can silently overwrite another app's generated TypeScript type with no error. `backend/tests/test_api_schema_names.py` enforces this; don't disable it.
- **IDs are UUIDv7** (via `uuid6.uuid7()`), never auto-increment integers — they're exposed in URLs and MCP tool output and shouldn't leak row-creation order or count.
- **Ownership, plus one narrow sharing boundary.** Every domain row is scoped to the user who created it (`created_by` via `OwnedModel`). The friend graph in `apps/social` is the only thing that crosses that line, and it grants exactly one capability: an accepted friend may *write* an `ExerciseEntry` to your account when you work out together. It grants no cross-user **reads** — a friend cannot see your entries, metrics, charts or days, and MCP stays self-only (the `social:*` scopes are not in the `claude` token bundles). `apps.social.services` is the single place that decides whether two users may interact, so blocking is enforced once rather than per feature; don't reimplement that check in a router. Anything wider (a shared timeline, likes, comments) is deliberately deferred — see `docs/roadmap-social.md` before extending the graph.
- **Auth.** Two auth backends, tried in order: session cookie + CSRF for the browser (`SessionAuthUnlessBearer`), then bearer token for everything else (`TokenAuth`, tokens prefixed `shos_pat_`, scoped e.g. `health:read`/`health:write`). Every router is authenticated by default; opt out explicitly with `auth=None` only for endpoints that must be reachable pre-login (login, signup, csrf). **Do not add password complexity/length validation** — `AUTH_PASSWORD_VALIDATORS` is intentionally empty; this is a self-hosted app and the account is the operator's own.
- **The frontend has no UI kit, form library, date-picker, or charting library, on purpose.** Charts are server-rendered static SVG using the `--viz-1..8` CSS custom properties in `globals.css`; birthdate uses a plain native `<input type="date">`. Don't introduce a component/charting dependency without a real reason — see `frontend/src/app/charts.tsx` for why Recharts was rejected (it would force client-rendering for interactivity nobody needs).

## Domain traps — do not "simplify" these

The Health domain encodes debugged bugs and cited research thresholds. If you touch any of the following, read the existing code and comments first — a plausible-looking simplification here reintroduces a known bug:

- **Timezone handling:** `local_date` is stored (not computed) on every time-bearing row. Historical Fitbit-sourced data has a documented UTC-encoding quirk handled in `timeutils.py` — never parse a Fitbit timestamp as plain epoch without going through the helpers there. Day-boundary queries build UTC bounds from the local timezone explicitly; never use SQL `date_trunc` for "what happened today."
- **`DailyMetric.source` (`device` vs `derived`):** `device` rows (from Fitbit's own daily summary) are authoritative and must never be overwritten by the rollup job; `derived` rows are entirely owned by the rollup job. Deciding which is which by metric name instead of the `source` column either clobbers real data or freezes a derived value forever.
- **Zero vs. absent:** some Fitbit fields are stored as literal `0.0` on days they weren't measured. Summing them directly makes an unmeasured day look like the worst day. Return `None`, not `0`, when nothing was actually reported.
- **`scoring.py`:** every scored metric is a piecewise-linear curve through explicit, cited anchor points — not a min/max linear ramp. The anchors encode literature-backed thresholds; don't "round" or re-derive them.
- **Habit streaks** count back from *yesterday* if today isn't ticked yet — counting from today makes an intact streak read as broken every morning until you check something off.
- **Fitbit OAuth token refresh:** refresh tokens are single-use and rotate. The new token must commit in the *same transaction* that spends the old one (row-locked via `select_for_update()`), and a failed/expired grant must be marked `EXPIRED` *outside* the failing transaction — marking it inside means the rollback silently keeps it looking healthy while every subsequent sync fails.
- **Partner-logged workouts:** one completed clip fans out to an `ExerciseEntry` per participant. Call `log_exercise` once per person so each row's `local_date` comes from *that person's* `timeutils.tz_for()` — never copy the actor's, since `local_date` is stored, not computed, and two friends in different timezones genuinely belong to different calendar days. Partner rows get `client_id=None`: `client_id` is globally unique and devicesync rejects one presented by a different user, so reusing a single id across the fan-out corrupts phone sync. `coop_group_id` is the grouping key. Two people in one room both pressing Complete is the *intended* use case, so the ~90s same-name dedupe in the service is load-bearing, not defensive.
- **Devicesync merge semantics:** `client_id` is a global identity key (not per-user) — a `client_id` presented by a different user than its existing row's owner is rejected, never overwritten. Deletes are tombstones (`deleted_at`), never hard deletes. Last-write-wins is decided by `client_updated_at`, not server receipt order.

## Testing

- `pytest` runs against a real Postgres test database (see `settings/test.py`), not sqlite — some queries rely on Postgres-specific behavior.
- Tests are written to pin failure modes (wrong timezone, a clobbered rollup, a leaked secret), not just happy paths. When fixing a bug, add the test that would have caught it before fixing the code.
- **Editing a model's `choices=` label (or anything else about a field) without regenerating its migration passes `pytest` locally** — your dev DB already has the old migration state applied — **and only breaks on a clean install.** `python manage.py makemigrations --check --dry-run` is what actually catches this; CI runs it, run it yourself before pushing if you touched a `models.py`.

## CI/CD

Three GitHub Actions workflows, in `.github/workflows/`:
- **`ci.yml`** — ruff (check + format), the migration-drift check above, and pytest for the backend; typecheck + build for the frontend. Runs on every PR, and is also called by `docker-publish.yml` as a gate.
- **`compose-smoke.yml`** — PR-only. Builds the real images, runs the real `docker compose up`, migrates, and hits the live stack (signup, login, the Health API, and `/mcp`) the way an operator actually would. Also regenerates `schema.d.ts` against the live backend and fails if it differs from what's committed — the guardrail for the "forgot to regenerate the frontend types" mistake. This is the check most likely to catch an integration-layer bug unit tests can't see: it exists because building this stack surfaced exactly that kind of bug twice — `DJANGO_ALLOWED_HOSTS` missing `127.0.0.1` left django's own healthcheck permanently failing (which cascaded into `next` never starting at all), and the MCP settings page generated a `/mcp` URL that `next.config.ts`'s rewrites didn't actually forward anywhere.
- **`docker-publish.yml`** — on push to `main` and on `v*.*.*` tags: runs `ci.yml` first, then builds and pushes `backend`/`frontend` images to `ghcr.io/<owner>/selfhealthos-{backend,frontend}`, tagged `latest` (main only), the short commit SHA, and the version (tag pushes only).

## Deployment

`docker compose up -d` with a filled-in `.env` is the whole story — see `.env.example` for required values (compose uses `${VAR:?required}` so missing config fails fast rather than silently defaulting). Pushing to `main` builds and publishes `backend`/`frontend` images to GHCR via GitHub Actions; there is no automatic deploy step — operators pull the new images and restart their own stack on their own schedule.

No bundled reverse proxy — the stack serves plain HTTP by default. If you front selfhealthos with your own reverse proxy (Traefik, nginx, a tunnel) for public HTTPS, that's a fully supported pattern; see the docs site's self-hosting guide. The MCP endpoint doesn't need TLS either way — Claude Code connects to `http://` MCP servers with no special configuration.
