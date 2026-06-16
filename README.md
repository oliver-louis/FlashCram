# FlashCram

FlashCram is a self-hosted, single-user, mobile-first flashcard app for exam cram. Phase 0 contains the Django scaffold, data model, admin, Docker runtime, and tests.
The current app supports deck/card CRUD, manual review modes, bulk text import, JSON backup import/export, and server-persisted settings.

## Run With Docker

```bash
docker compose up --build
```

The app serves at [http://localhost:8000](http://localhost:8000). Django admin is available at `/admin/`.
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
python manage.py migrate
python manage.py test
python manage.py runserver
```

The Docker image builds Tailwind CSS and daisyUI in a Node build stage, then copies the compiled CSS and vendored HTMX/Alpine files into the final Python image. No Node or CDN dependency is required at runtime.

## Environment

Useful variables:

- `DATABASE_URL`, defaulting locally to `sqlite:///db.sqlite3`
- `DJANGO_SECRET_KEY`, defaulting to a development-only value
- `DEBUG`, defaulting locally to `True`; Docker Compose sets it to `False`
- `ALLOWED_HOSTS`, comma-separated, defaulting to local hosts

## Phase Scope

This MVP intentionally does not include auth, markdown rendering, sync, or offline/PWA features.
