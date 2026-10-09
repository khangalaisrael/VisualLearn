"""SQLAlchemy ORM models.

`users`, `presentations`, `slides` — Milestone 1 (docs/ROADMAP.md).
`cache_entries` — Milestone 2's analysis cache (docs/ARCHITECTURE.md §5).
`objects`, `conversations`, `messages` — Milestone 3 chat (ChatService,
POST /chat) needs a queryable source for Figure/Slide-mode grounding, which
JSON-in-cache alone doesn't provide (see api/v1/slides.py's `analyze_slide`
for where objects are persisted).

docs/DATA_MODEL.md documents the full target schema; `embeddings` is still
deliberately not created yet — it arrives with M4 retrieval, so pgvector
setup lands with the feature that needs it.

Every timestamp column below is explicitly `DateTime(timezone=True)`,
matching the `TIMESTAMPTZ` columns declared in alembic/versions/. Without
that explicit type, SQLAlchemy infers a naive `DateTime` from the Python
`datetime` annotation alone — which compiles bind parameters as
`::TIMESTAMP WITHOUT TIME ZONE` regardless of what the real column type is,
and asyncpg then rejects a timezone-aware Python value (`datetime.now(UTC)`)
bound against that mismatched cast. SQLite (used in tests) doesn't enforce
this distinction, which is why this only surfaced against real PostgreSQL.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import GUID


class User(Base):
    """Placeholder for hosted multi-tenant mode (see ADR-007). Unpopulated
    while the product runs local-first — every row below has a nullable
    `user_id` so hosting later is additive, not a migration."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Presentation(Base):
    __tablename__ = "presentations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32))  # "live_capture" | "uploaded_deck"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    slides: Mapped[list["Slide"]] = relationship(back_populates="presentation", cascade="all, delete-orphan")


class Slide(Base):
    __tablename__ = "slides"
    __table_args__ = (
        UniqueConstraint("presentation_id", "image_hash", name="uq_slide_presentation_image_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    presentation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("presentations.id"))
    slide_number: Mapped[int]
    image_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex digest, server-computed
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | analyzed | failed
    summary: Mapped[str | None] = mapped_column(nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    presentation: Mapped["Presentation"] = relationship(back_populates="slides")


class CacheEntry(Base):
    """Durable backing store for the Redis analysis cache
    (app/services/cache_service.py) — see docs/DATA_MODEL.md `cache_entries`
    and docs/ARCHITECTURE.md §5. Keyed globally by image hash, independent
    of any single presentation or slide, so an identical screenshot
    reappearing in a different deck still skips the model call — and scoped
    by `model_used` too, so a gpt-4o-mini result never gets served for a
    gpt-4o request or vice versa (see the extension's model picker).
    """

    __tablename__ = "cache_entries"
    __table_args__ = (
        UniqueConstraint("image_hash", "model_used", name="uq_cache_entry_image_hash_model_used"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    image_hash: Mapped[str] = mapped_column(String(64))
    slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("slides.id"), nullable=True)
    analysis_result: Mapped[dict] = mapped_column(JSON)
    model_used: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ObjectRecord(Base):
    """A single extracted object (title/paragraph/equation/diagram/graph/
    table/image) from one slide's analysis — see docs/DATA_MODEL.md
    `objects`. Persisted once, when a slide is first analyzed
    (api/v1/slides.py), with the same `id` the client already holds from
    the analyze response, so a later Figure/Slide-mode chat request's
    `object_id`/`slide_id` resolves to this row directly.
    """

    __tablename__ = "objects"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("slides.id"))
    type: Mapped[str] = mapped_column(String(32))
    bounding_box: Mapped[dict] = mapped_column(JSON)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latex: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    # Deviation from docs/DATA_MODEL.md's original draft (predates ADR-010):
    # SlideObject already carries graph_structure, so it's persisted here too.
    graph_structure: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    """One chat thread — see docs/DATA_MODEL.md `conversations`.
    `presentation_id` is nullable for a future General-mode chat with no
    slide grounding at all (not exercised by Figure/Slide modes, M3's
    scope, which always have a presentation)."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("presentations.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """One turn in a conversation — see docs/DATA_MODEL.md `messages`.
    `referenced_object_ids` lets the Ask tab render citation links back to
    the overlay (Premium UI Guide's Chat UX) without re-deriving which
    objects were actually shown to the model for this turn."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    query_mode: Mapped[str] = mapped_column(String(16))
    referenced_object_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
