# FlashCram

FlashCram is a self-hosted, single-user, mobile-first flashcard app for exam cram.
The current app supports deck/card CRUD, manual review modes, card search/filter, bulk text import, JSON backup import/export, markdown/LaTeX/code rendering, one optional image per card, server-persisted settings, and install-only PWA metadata.

## Run With Docker

```bash
docker compose up --build
```

The app serves at [http://localhost:8000](http://localhost:8000). Django admin is available at `/admin/`.
Docker binds the app to all host interfaces, so devices on the same LAN can use your computer's local IP, for example `http://192.168.1.23:8000`.
If that does not load from your phone, check that both devices are on the same network and that your computer firewall allows incoming connections to port `8000`.

If port `8000` is already in use, run with another host port:

```bash
HOST_PORT=8001 docker compose up --build
```

SQLite is stored on the `flashcram-data` named volume at `/data/flashcram.sqlite3` inside the container. The app reads its database from `DATABASE_URL`.

Useful app routes:

- `/` — deck list
- `/bulk-import/` — paste-import cards into an existing or new deck
- `/settings/` — theme, weak-card thresholds, random weighting, and JSON backup/import

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

Compiled CSS and vendored HTMX/Alpine files are committed under `static/` so local `runserver` starts styled immediately. Run `npm run build:assets` after changing templates, forms, `static_src/input.css`, or frontend package versions.

The Docker image uses the same asset build script in a Node build stage, then copies the compiled files into the final Python image. No Node or CDN dependency is required at runtime. KaTeX, MathLive, Pygments CSS, HTMX, and Alpine are served from `static/vendor/`.

## Rich Card Content

Cards can be either plain text or markdown. Plain text cards are not processed, so shell snippets like `$HOME`, `*`, and `_` remain literal. Markdown cards support fenced code blocks, tables, and math using `\(...\)`, `\[...\]`, or `$$...$$`; bare `$...$` math is intentionally disabled.

Each card may have one optional image assigned to the front or back. Uploads accept PNG, JPEG, WEBP, or GIF. Static raster images are downscaled with Pillow before being stored in the database; full JSON backup/export includes the image as base64.

## Environment

Useful variables:

- `DATABASE_URL`, defaulting locally to `sqlite:///db.sqlite3`
- `DJANGO_SECRET_KEY`, defaulting to a development-only value
- `DEBUG`, defaulting locally to `True`; Docker Compose sets it to `False`
- `ALLOWED_HOSTS`, comma-separated, defaulting locally to local hosts; Docker Compose defaults to `*` for LAN self-hosting
- `CSRF_TRUSTED_ORIGINS`, comma-separated, optional for stricter reverse-proxy or HTTPS deployments

## Phase Scope

This MVP intentionally does not include auth, markdown rendering, sync, or offline/PWA features.
The included web manifest is only for home-screen installability; there is no service worker or offline data cache.
