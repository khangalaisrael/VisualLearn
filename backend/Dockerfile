# Build context is the repo root (see docker-compose.yml: context: .,
# dockerfile: backend/Dockerfile) — not ./backend as in Sprint 1. This is
# required so the image can include the top-level prompts/ directory
# alongside backend/, and it's why every COPY below is prefixed with
# `backend/` or `prompts/`.
#
# WORKDIR is /workspace, and `backend/` is kept as a real subdirectory
# inside it (not flattened) so the final layout is
# /workspace/backend/app/... next to /workspace/prompts/ — the exact same
# relative nesting as the local repo (<repo>/backend/app/... next to
# <repo>/prompts/). app/core/prompt_loader.py resolves the prompts
# directory via `Path(__file__).resolve().parents[3]`, which only gives the
# right answer if that nesting matches in both environments.
FROM python:3.12-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
COPY backend/alembic.ini backend/alembic.ini
COPY backend/alembic backend/alembic
COPY prompts prompts

RUN pip install --upgrade pip && pip install ./backend

WORKDIR /workspace/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
