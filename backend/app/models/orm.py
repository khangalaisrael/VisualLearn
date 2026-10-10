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

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import GUID


class User(Base):
    """Hosted multi-tenant mode (see ADR-007, docs/PublicHostingMVP.md Phase
    2). Unpopulated while the product runs purely local-first — every other
    table's `user_id` is nullable, so this is additive, not a migration, for
    anyone still on the local-only flow. `google_sub` is Google's stable
    per-account identifier (the OAuth `sub` claim) — the lookup key for
    sign-in, since a Google account's email can change but `sub` doesn't."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    """A signed-in session issued after Google sign-in (Phase 2). `token` is
    a random opaque string (same "boring, inspectable" style as
    `LOCAL_API_KEY` — see ADR-007 — not a JWT: revocation is just a DB
    delete, no signing-key rotation story to build). The extension sends it
    as `Authorization: Bearer <token>`, additive to the existing `X-API-Key`
    check per docs/API_CONTRACT.md, not a replacement for it."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RateLimitEvent(Base):
    """One row per rate-limited action actually performed (Phase 4,
    docs/PublicHostingMVP.md). Backed by Postgres, not Redis — Redis/
    Upstash isn't actually configured on the live deployment yet, and
    unlike cache_service.py's analysis cache (a pure speed optimization
    that's fine to degrade on a Redis outage), a rate limit that silently
    stops enforcing itself on a cache miss would defeat its entire
    purpose. A small daily volume of rows per key is cheap to count.

    `key` is `"user:<uuid>"` for a signed-in request or `"ip:<address>"`
    for an anonymous one (Phase 4's own goal explicitly includes "a bot
    hitting the API directly, bypassing the extension" — which has no
    session token at all, so IP is the only thing left to key on)."""

    __tablename__ = "rate_limit_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # "analyze" | "chat"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageEvent(Base):
    """One billable (or blocked) action: a capture, a chat message, or a
    limit hit. Backs the admin view (spend per user, outliers, demand).

    Deliberately NOT cleaned up by the 30-day content retention, and
    `slide_id` / `conversation_id` are plain columns, not foreign keys, so
    deleting a chat or slide never touches spend history. Deleting an
    account anonymises its rows (`user_id` -> NULL) instead of removing
    them. `est_cost_usd` is an estimate from a price table, not a bill."""

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    # "analyze" | "chat" | "limit_hit_daily" | "limit_hit_monthly" | "limit_hit_global"
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProWaitlistClick(Base):
    """One click on "Join the Pro waitlist". Signed-in users only, so the
    interested person can be emailed. Clicks, not people: repeat clicks are
    kept (distinct users are counted at read time)."""

    __tablename__ = "pro_waitlist_clicks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "daily" | "monthly" | "settings"
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
    # The slide this chat is about, so a reopened chat can restore the
    # slide's extracted objects alongside its messages.
    slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("slides.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Bumped on every chat turn; retention (services/retention.py) counts
    # from here, so an active chat never expires mid-use.
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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
