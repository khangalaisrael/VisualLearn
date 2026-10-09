# Backend image for a hosted platform that builds from the repo root and
# injects $PORT — Render's free web service (render.yaml,
# docs/DEPLOY_RENDER.md). Same backend/ + prompts/ layout as
# backend/Dockerfile (see its header comment for why the nesting matters);
# differs only in the entrypoint, which applies migrations before serving.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
COPY backend/alembic.ini backend/alembic.ini
COPY backend/alembic backend/alembic
COPY prompts prompts
COPY deploy/hosted/start.sh start.sh

RUN pip install --upgrade pip && pip install ./backend && chmod +x start.sh

RUN useradd -m -u 1000 app
USER app

WORKDIR /workspace/backend

CMD ["/workspace/start.sh"]
