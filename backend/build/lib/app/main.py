"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(title="VisionLearn AI Backend", version="0.1.0")

# CORS is intentionally wide open: the extension's origin
# (chrome-extension://<id>) isn't known ahead of install, and Starlette's
# CORSMiddleware only does exact-string matching (no wildcard patterns other
# than "*"). Per docs/adr/ADR-007-local-first-deployment.md, the actual
# access control for this locally-run, single-user backend is the
# `X-API-Key` header (see app/api/deps.py:verify_api_key), not CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

app.include_router(api_router, prefix="/api/v1")
