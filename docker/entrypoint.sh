#!/bin/sh
set -eu

python manage.py wait_for_db
if [ -n "${FLASHCRAM_MIGRATE_TARGET:-}" ]; then
  python manage.py migrate ${FLASHCRAM_MIGRATE_TARGET} --noinput
else
  python manage.py migrate --noinput
fi
python manage.py ensure_superuser_from_env
python manage.py collectstatic --noinput

exec "$@"
