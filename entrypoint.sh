#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting muse worker..."
exec python -m muse.main "$@"
