#!/bin/sh
# Container entrypoint for the Hugging Face Space (deploy/huggingface/Dockerfile).
# Applies pending migrations first — a Space has no shell step between
# deploy and start — then serves on the Space's app_port.
set -e

cd /workspace/backend
alembic upgrade head

# --proxy-headers: the Space sits behind Hugging Face's HTTPS proxy.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}" --workers 2 --proxy-headers --forwarded-allow-ips "*"
