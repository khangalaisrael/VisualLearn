"""Aggregates all v1 routers under a single include point for app/main.py."""

from fastapi import APIRouter

from app.api.v1 import auth, chat, conversations, health, slides, usage

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(slides.router)
api_router.include_router(chat.router)
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(usage.router)
