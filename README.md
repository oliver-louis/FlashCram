# FlashCram

FlashCram is a self-hosted, multi-user, mobile-first flashcard app for exam cram.
It is built for fast card creation, manual review, and comfortable phone use on a homelab or private server, with local admin-created accounts and optional app-level OIDC login for Authentik-style deployments.

## Features

- Deck and card CRUD with server-rendered Django templates.
- Modal card editor with Markdown shortcuts/toolbars, review-style draft preview, and Save and add another.
- Optional deck categories, pin/favourite indicators, and reversible deck archiving.
- Mobile-first review sessions with all, random, weak, unseen, hidden, and tag-based modes.
- Correct/incorrect counters, weak-card detection, undo, skip, show-less, hide, and marked-card workflows.
- Card search/filter by text, tag, status, and marked state.
- Bulk raw-text import and authoring JSON import for LLM-generated flashcards.
- Full JSON backup export/import from Settings.
- Plaintext and markdown cards, with fenced code blocks, tables, KaTeX-ready LaTeX, and Pygments highlighting.
- One optional image per card, stored in the database and included in full backups.
- Server-persisted dark/light theme and install-only PWA metadata.

## Writing Cards By Hand

From a deck, select **Add card** or a card's **Edit** action. The editor opens in a modal; direct editor links also work as full pages.

- Choose **Plain text** for literal text, or **Markdown** for formatting. Switching modes preserves the text.
- In Markdown, use the toolbar or **Ctrl/Cmd+B** and **Ctrl/Cmd+I**. Select text to format it, or toggle formatting on before typing and off when finished. **Ctrl/Cmd+Z** undoes typing and editor commands.
- List buttons format selected lines. Typing `- ` or `1. ` after prose adds the blank line required by the renderer; Enter continues the list, and Enter on an empty item ends it. Pasted Markdown is preserved, so include a blank line before pasted lists.
- **Insert equation** keeps the MathLive keyboard and inserts into the last focused face. Inline math uses `\(...\)` and display math uses `\[...\]`; bare dollar signs remain literal.
- **Preview card** shows both faces and the current image as a flippable card without saving or changing review counters. **Back to editing** restores the draft.
- **Save and add another** retains format and tags, clears the content/image, resets status to Normal, and focuses Front. Status lives under **More options**.
- New image attachments show a thumbnail and can be removed before saving. Failed validation and preview requests preserve the draft and selected file. Unsaved edits prompt before closing; drafts are not stored across browser sessions.

Authoring JSON imports, New Deck JSON uploads, and full backup imports/exports remain separate workflows with unchanged schemas and rendering.

## Stack

- Django, server-rendered templates, HTMX, Alpine.js.
- Tailwind CSS + daisyUI compiled into static assets.
- Postgres for production via Docker Compose profile; SQLite remains useful for local development and one-time migration exports.
- Docker Compose with one app container plus a profiles-gated Postgres service.

There is no runtime CDN and no Node.js in the final app container.

## Quick Start With Docker

```bash
git clone <your-repo-url> flashcram
cd flashcram
cp .env.example .env
```

Edit `.env` before the first start. At minimum, set a real `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, and `ALLOWED_HOSTS`. For a fresh server, also configure either Authentik/OIDC or `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` so you have a first account to log in with.

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Start the app with Postgres:

```bash
COMPOSE_PROFILES=postgres docker compose up --build -d
```

The app runs on [http://localhost:8000](http://localhost:8000) by default. On another device on the same LAN, use your server IP, for example `http://192.168.1.23:8000`.

Useful commands:

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

Use another host port if `8000` is already taken:

```bash
HOST_PORT=8001 docker compose up --build -d
```

## Server Deployment

For a fresh server with no database migration:

1. Pull the repo and copy `.env.example` to `.env`.
2. Set `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DATABASE_URL`, and `ALLOWED_HOSTS`.
3. Configure OIDC values, or set `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD` for a first local admin.
4. Run `COMPOSE_PROFILES=postgres docker compose up --build -d`.
5. Log in, then use Settings -> Import all or Bulk import -> JSON Import to bring in exported decks.

Recommended first-server `.env`:

```env
DEBUG=False
DJANGO_SECRET_KEY=replace-with-a-real-secret
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.23,flashcram.example.com
DATABASE_URL=postgres://flashcram:replace-this-postgres-password@postgres:5432/flashcram
POSTGRES_DB=flashcram
POSTGRES_USER=flashcram
POSTGRES_PASSWORD=replace-this-postgres-password
HOST_PORT=8000
OIDC_RP_CLIENT_ID=your-authentik-client-id
OIDC_RP_CLIENT_SECRET=your-authentik-client-secret
OIDC_OP_AUTHORIZATION_ENDPOINT=https://auth.example.com/application/o/flashcram/authorize/
OIDC_OP_TOKEN_ENDPOINT=https://auth.example.com/application/o/flashcram/token/
OIDC_OP_USER_ENDPOINT=https://auth.example.com/application/o/flashcram/userinfo/
OIDC_OP_JWKS_ENDPOINT=https://auth.example.com/application/o/flashcram/jwks/
SESSION_EXPIRE_DAYS=5
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=replace-with-a-temporary-strong-password
```

In Authentik, set the redirect URI to:

```text
https://flashcram.example.com/oidc/callback/
```

FlashCram has its own `/login/` page. Users can sign in with an admin-created local username/password account, or explicitly choose “Sign in with Authentik” to start the OIDC flow. There is no self-registration, password reset, or account linking.

Logout is a POST-only action in Settings -> Account settings. Sessions are non-rolling and expire after `SESSION_EXPIRE_DAYS` days, defaulting to 5.

If you set `DJANGO_SUPERUSER_PASSWORD` only for first boot, remove it from `.env` after confirming you can log in; the existing account remains in Postgres.

## Reverse Proxy

Run the container on the host, then proxy to `127.0.0.1:8000`. FlashCram expects to be served from `/` on its own host or subdomain.

For HTTPS behind a reverse proxy, set:

```env
ALLOWED_HOSTS=flashcram.example.com
CSRF_TRUSTED_ORIGINS=https://flashcram.example.com
USE_X_FORWARDED_HOST=True
SECURE_PROXY_SSL_HEADER=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SESSION_EXPIRE_DAYS=5
```

Make sure your proxy forwards the original host and protocol. Minimal Nginx example:

```nginx
server {
    server_name flashcram.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Minimal Caddy example:

```caddyfile
flashcram.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

If your proxy and Docker host are different machines, proxy to `http://<docker-host-ip>:8000` and keep the Docker host firewall scoped to trusted networks.

## Data And Backups

Postgres data lives in the `flashcram-postgres` Docker volume. Use `pg_dump` for production backups.

For app-level backups, use Settings -> Export all. That JSON includes decks, cards, counters, markdown/plaintext formats, tags, and card images.

For database backups:

```bash
docker compose exec postgres pg_dump -U flashcram flashcram > flashcram.sql
```

The exact volume name may differ if your checkout directory is not named `flashcram`; check with `docker volume ls`.

## SQLite To Postgres Migration

If you already have a pre-P6 SQLite install:

```bash
# 1. On the old SQLite config, export data.
docker compose exec app python manage.py dumpdata cards --natural-foreign --natural-primary --indent 2 > flashcram-sqlite-cards.json

# 2. Update .env to Postgres DATABASE_URL and start only through the nullable-owner migration.
COMPOSE_PROFILES=postgres FLASHCRAM_MIGRATE_TARGET="cards 0006_multi_user_nullable" docker compose up --build -d

# 3. Load the old data.
docker compose exec -T app python manage.py loaddata < flashcram-sqlite-cards.json

# 4. Create or provision the target user, then assign old single-user data.
docker compose exec app python manage.py createsuperuser
docker compose exec app python manage.py assign_orphan_decks <username>

# 5. Finish migrations and verify row counts.
docker compose exec app python manage.py migrate
docker compose exec app python manage.py shell -c "from cards.models import Deck,Card; print(Deck.objects.count(), Card.objects.count())"
```

## Upgrades

```bash
git pull
docker compose up --build -d
docker compose logs -f app
```

The container runs Django migrations and `collectstatic` on startup.

## Environment Variables

| Variable | Default | Notes |
| --- | --- | --- |
| `HOST_PORT` | `8000` | Host port mapped to the app container. |
| `DEBUG` | `False` in Compose | Keep `False` on a server. |
| `DJANGO_SECRET_KEY` | Development placeholder | Replace before deployment. |
| `ALLOWED_HOSTS` | `*` in Compose | Use explicit server IPs/hostnames for stricter deployments. |
| `CSRF_TRUSTED_ORIGINS` | empty | Required for HTTPS form posts behind a proxy. |
| `DATABASE_URL` | Postgres URL in `.env.example` | Use Postgres for deployment; SQLite is only for local/dev export paths. |
| `POSTGRES_DB` | `flashcram` | Database name for the Compose Postgres profile. |
| `POSTGRES_USER` | `flashcram` | Database user for the Compose Postgres profile. |
| `POSTGRES_PASSWORD` | `flashcram` | Change before deployment. |
| `OIDC_RP_CLIENT_ID` | empty | Authentik/OIDC client ID. |
| `OIDC_RP_CLIENT_SECRET` | empty | Authentik/OIDC client secret; never commit real values. |
| `OIDC_OP_AUTHORIZATION_ENDPOINT` | empty | OIDC authorization endpoint. |
| `OIDC_OP_TOKEN_ENDPOINT` | empty | OIDC token endpoint. |
| `OIDC_OP_USER_ENDPOINT` | empty | OIDC userinfo endpoint. |
| `OIDC_OP_JWKS_ENDPOINT` | empty | OIDC JWKS endpoint. |
| `DJANGO_SUPERUSER_USERNAME` | empty | Optional idempotent first-admin creation. |
| `DJANGO_SUPERUSER_PASSWORD` | empty | Optional first-admin password. |
| `USE_X_FORWARDED_HOST` | `False` | Set `True` behind a trusted reverse proxy if needed. |
| `SECURE_PROXY_SSL_HEADER` | `False` | Set `True` when the proxy sends `X-Forwarded-Proto: https`. |
| `SESSION_COOKIE_SECURE` | `False` | Set `True` for HTTPS-only sessions. |
| `CSRF_COOKIE_SECURE` | `False` | Set `True` for HTTPS-only CSRF cookies. |
| `SECURE_SSL_REDIRECT` | `False` | Usually leave redirecting to your proxy; enable only if wanted. |

## Health Check

Docker checks:

```text
/healthz/
```

It returns `ok` when Django is serving requests.

## Local Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
npm install
npm run build:assets
python manage.py migrate
python manage.py test
python manage.py runserver
```

Compiled CSS and vendored HTMX/Alpine/KaTeX/MathLive assets are committed under `static/`, so `runserver` starts styled immediately. Run `npm run build:assets` after changing templates, forms, `static_src/input.css`, or frontend package versions.

## Tests

```bash
.venv/bin/python manage.py test
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
node --test tests/card-editor.test.cjs
npm run build:assets
```

## Rich Card Content

Cards can be plaintext or markdown. Plaintext cards are escaped and not processed, so shell snippets like `$HOME`, `*`, and `_` remain literal.

Markdown cards support fenced code blocks, tables, and math with `\(...\)`, `\[...\]`, or `$$...$$`. Bare `$...$` math is intentionally disabled.

Each card may have one optional image assigned to the front or back. Uploads accept PNG, JPEG, WEBP, or GIF. Raster images are downscaled with Pillow before storage.

## Security Notes

FlashCram requires authenticated users for app pages. Local users are created by an admin; OIDC users are provisioned through Authentik when that login path is configured. Use HTTPS for WAN access, set `DEBUG=False`, change `DJANGO_SECRET_KEY`, use a strong Postgres password, configure `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` for your public hostname, and keep `SESSION_EXPIRE_DAYS` bounded.

## Project Status

Completed phases include the Django/Docker scaffold, CRUD, review modes, import/export, mobile polish, markdown/LaTeX/code rendering, images, marked cards, review/deck UX refinements, deck organization, Postgres, OIDC auth, local admin-created login, logout, bounded sessions, and per-user data scoping.

## License

No license file has been added yet.
