#!/bin/sh
set -e
# Ingest single SSM parameter APP_ENV_CONFIG if provided
if [ -n "$APP_ENV_CONFIG" ]; then
    echo "[Entrypoint] Ingesting APP_ENV_CONFIG into /app/.env..."
    printf "%s\n" "$APP_ENV_CONFIG" > /app/.env
    chmod 600 /app/.env 2>/dev/null || true
    set -a
    . /app/.env
    set +a
fi


if [ "${AUTO_MIGRATE:-true}" = "true" ] || [ "${AUTO_MIGRATE:-true}" = "1" ]; then
    echo "[Entrypoint] Running database migrations..."
    python manage.py migrate --noinput || echo "[Entrypoint] Warning: Database migration failed, continuing boot..."
fi

# Collect static files if AUTO_COLLECTSTATIC is enabled
if [ "${AUTO_COLLECTSTATIC:-true}" = "true" ] || [ "${AUTO_COLLECTSTATIC:-true}" = "1" ]; then
    echo "[Entrypoint] Collecting static assets..."
    python manage.py collectstatic --noinput || echo "[Entrypoint] Static collection completed."
fi

echo "[Entrypoint] Starting application process: $@"
exec "$@"
