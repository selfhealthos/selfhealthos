# selfhealthos

**selfhealthos** is a self-hosted, open-source nutrition and fitness tracker you run yourself with Docker Compose. It's built for people who want a real dashboard over their health data — sleep, activity, heart rate, food, habits, body measurements, lab results — without handing that data to a third party.

Documentation: https://selfhealthos.github.io

## Features

- **Multi-user**, self-serve signup — username/password only for local accounts (no password complexity rules; this is a homelab app, `admin`/`admin` is fine if that's what you want).
- A **Health dashboard** as the home page: daily summary, trends, a scored heatmap, sleep architecture (hypnogram, oxygen, sleep score), heart rate (resting HR, HRV, zones), step/activity tracking, food diary with keyword-based flagging, gut/Bristol tracking, habits with streaks, body measurements, lab results, notes, and documents.
- **Fitbit sync** via OAuth — connect your account in Settings and background jobs pull your data in.
- **User settings**: manage your Fitbit connection, generate scoped API access tokens, and get a ready-to-run command to install this instance's data as an MCP server in Claude Code.
- A **friendly, interactive API** (Swagger UI) for every endpoint, plus an **MCP endpoint** so Claude (or any MCP client) can query your own data directly.
- **Profile page** with a photo and your birthdate; account settings feed the age/sex-personalized scoring used across the dashboard.

## Stack

- **Backend:** Django + [django-ninja](https://django-ninja.dev/) (REST API with auto-generated OpenAPI/Swagger docs), Postgres, Redis + Celery for background jobs (Fitbit sync).
- **Frontend:** Next.js (App Router), no UI kit or charting library — dashboards are server-rendered.
- **MCP:** a Streamable HTTP MCP server backed by the same service layer as the REST API.
- **Deployment:** a single `docker compose up`, no reverse proxy bundled — plain HTTP by default, front it with your own (Traefik, nginx, a tunnel) if you want public HTTPS.

## Quick start

```bash
git clone https://github.com/selfhealthos/selfhealthos.git
cd selfhealthos
cp .env.example .env              # defaults work as-is except the two noted inside
docker compose up -d
docker compose exec django python manage.py migrate
```

Then open `http://localhost` and sign up. Full setup and configuration docs: https://selfhealthos.github.io/docs/getting-started/installation

## Development

See [CLAUDE.md](./CLAUDE.md) for the local dev workflow, architecture conventions, and testing.

## License

selfhealthos is licensed under the **GNU Affero General Public License v3.0** (AGPLv3) — see [LICENSE](./LICENSE). In short: you're free to self-host, use, and modify it, and if you run a modified version as a network service you must make that modified source available to its users. This license does not permit repackaging and reselling the software (or a hosted version of it) as a commercial product without complying with those same terms.

A hosted, paid version of selfhealthos may be offered separately by the project maintainer in the future; that does not change the terms above for self-hosters.
