# Hugging Face Docker Space image for the backend (docs/DEPLOY_HF.md).
# Not built from the repo root directly: .github/workflows/deploy-hf-space.yml
# assembles a Space folder containing this file, start.sh, the Space
# README.md, backend/ and prompts/ — the same backend/ + prompts/ nesting
# backend/Dockerfile preserves (see its header comment for why).
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
COPY start.sh start.sh

RUN pip install --upgrade pip && pip install ./backend && chmod +x start.sh

# Spaces run containers as UID 1000; nothing here writes to disk at runtime.
RUN useradd -m -u 1000 user
USER user

WORKDIR /workspace/backend

# Spaces route public HTTPS traffic to app_port (README.md front matter).
EXPOSE 7860

CMD ["/workspace/start.sh"]
