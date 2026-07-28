"""Aggregates all v1 routers under a single include point for app/main.py."""

from fastapi import APIRouter

from app.api.v1 import chat, health, slides

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(slides.router)
api_router.include_router(chat.router)
