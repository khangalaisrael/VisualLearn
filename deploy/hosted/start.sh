#!/bin/sh
# Entrypoint for deploy/hosted/Dockerfile. Applies pending migrations first
# (a hosted platform has no shell step between deploy and start), then
# serves on the platform-provided $PORT.
set -e

cd /workspace/backend
alembic upgrade head

# One worker by default: Render's free instance has 512 MB RAM and 0.1 CPU,
# and the app is I/O-bound (waiting on the model API), so a single async
# worker handles concurrent captures. Raise WEB_CONCURRENCY on a bigger plan.
# --proxy-headers: the service sits behind the platform's HTTPS proxy.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" --proxy-headers --forwarded-allow-ips "*"
