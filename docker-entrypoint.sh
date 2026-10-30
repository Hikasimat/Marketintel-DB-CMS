#!/bin/sh
set -e

# Run database migrations if AUTO_MIGRATE is enabled or default to true on boot
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
