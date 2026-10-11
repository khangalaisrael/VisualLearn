"""Aggregates all v1 routers under a single include point for app/main.py."""

from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, conversations, health, notes, presentations, quizzes, series, slides, study_aids, usage

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(slides.router)
api_router.include_router(chat.router)
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(usage.router)
api_router.include_router(admin.router)
api_router.include_router(presentations.router)
api_router.include_router(series.router)
api_router.include_router(notes.router)
api_router.include_router(quizzes.router)
api_router.include_router(study_aids.router)
