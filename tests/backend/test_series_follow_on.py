"""The sorter's model call is skipped when a capture plainly continues the
lecture being captured (services/series.py `_follow_on`): the previous
capture was a lecture slide on the same page minutes ago, and this slide has
a heading of its own that is not the start of exercises."""

import io
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_series_sorter, get_slide_analyzer
from app.main import app
from app.models.orm import Slide, User
from app.models.orm import Session as SessionRow
from app.models.schemas import BoundingBox, SlideObject
from app.services.series_sorter import ExistingSeries, SlideDigest, SortDecision
from app.services.slide_analyzer import AnalysisResult

API_KEY = {"X-API-Key": "test-api-key"}
URL = "https://cs.example.edu/cs201/week-4"


class _TitledAnalyzer:
    """Reads the heading the test sets next as the slide's title."""

    model_name = "titled"

    def __init__(self) -> None:
        self.heading: str | None = None

    async def analyze(self, image_bytes: bytes) -> AnalysisResult:
        del image_bytes
        box = BoundingBox(x=0.05, y=0.05, width=0.9, height=0.1)
        objects = [SlideObject(id=str(uuid.uuid4()), type="paragraph", bounding_box=box, extracted_text="Body text.", confidence=0.9)]
        if self.heading:
            objects.insert(0, SlideObject(id=str(uuid.uuid4()), type="title", bounding_box=box, extracted_text=self.heading, confidence=0.9))
        return AnalysisResult(objects=objects, summary=f"About {self.heading or 'something'}.")


class _CountingSorter:
    model_name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    async def sort(self, slide: SlideDigest, existing: list[ExistingSeries], previous=None) -> SortDecision:
        self.calls += 1
        return SortDecision(
            existing_index=0 if existing else None,
            category="Algorithms",
            title="Divide and Conquer",
            subtopic=f"Sorted {self.calls}",
            kind="lecture",
        )


def _png(seed: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (seed * 37 % 256, seed * 59 % 256, seed * 83 % 256)).save(buffer, format="PNG")
    return buffer.getvalue()


class _Lecture:
    def __init__(self, client: AsyncClient, db: AsyncSession, headers: dict[str, str]) -> None:
        self.client, self.db, self.headers = client, db, headers
        self.analyzer, self.sorter = _TitledAnalyzer(), _CountingSorter()
        self.count = 0
        app.dependency_overrides[get_slide_analyzer] = lambda: self.analyzer
        app.dependency_overrides[get_series_sorter] = lambda: self.sorter

    async def capture(self, heading: str | None, url: str = URL, minutes_after_previous: float = 2) -> Slide:
        # Each earlier capture is moved back in time, so captures never tie on a timestamp.
        for earlier in (await self.db.execute(select(Slide))).scalars():
            stamp = earlier.created_at.replace(tzinfo=earlier.created_at.tzinfo or UTC)
            earlier.created_at = stamp - timedelta(minutes=minutes_after_previous)
        await self.db.commit()
        self.analyzer.heading = heading
        self.count += 1
        response = await self.client.post(
            "/api/v1/slides/analyze",
            files={"image": ("slide.png", _png(self.count), "image/png")},
            data={"slide_number": "1", "lecture_title": "Week 4", "page_url": url},
            headers=self.headers,
        )
        assert response.status_code == 200, response.text
        slide = await self.db.get(Slide, uuid.UUID(response.json()["slide_id"]))
        await self.db.refresh(slide)
        return slide


async def _signed_in(db: AsyncSession) -> dict[str, str]:
    user = User(id=uuid.uuid4(), google_sub="sub-follow", email="follow@example.com")
    db.add(user)
    await db.flush()
    db.add(SessionRow(id=uuid.uuid4(), user_id=user.id, token="token-follow", expires_at=datetime.now(UTC) + timedelta(days=1)))
    await db.commit()
    return {**API_KEY, "Authorization": "Bearer token-follow"}


async def test_the_next_slide_of_the_lecture_skips_the_sorter(client: AsyncClient, db_session: AsyncSession) -> None:
    lecture = _Lecture(client, db_session, await _signed_in(db_session))
    first = await lecture.capture("Merge Sort")
    assert lecture.sorter.calls == 1

    second = await lecture.capture("Running Time of Merge Sort")
    assert lecture.sorter.calls == 1  # no model call
    assert second.series_id == first.series_id
    assert second.subtopic == "Running Time of Merge Sort"
    assert second.content_kind == "lecture"


async def test_uncertain_captures_still_go_to_the_sorter(client: AsyncClient, db_session: AsyncSession) -> None:
    lecture = _Lecture(client, db_session, await _signed_in(db_session))
    await lecture.capture("Merge Sort")
    calls = lecture.sorter.calls

    await lecture.capture("Exercises")  # may be practice
    calls += 1
    assert lecture.sorter.calls == calls

    await lecture.capture("Binary Search", url="https://cs.example.edu/cs201/week-5")  # another page
    calls += 1
    assert lecture.sorter.calls == calls

    await lecture.capture("Heaps", url="https://cs.example.edu/cs201/week-5", minutes_after_previous=45)  # long after
    calls += 1
    assert lecture.sorter.calls == calls

    await lecture.capture(None, url="https://cs.example.edu/cs201/week-5")  # no heading of its own
    calls += 1
    assert lecture.sorter.calls == calls


async def test_a_signed_out_capture_is_never_sorted(client: AsyncClient, db_session: AsyncSession) -> None:
    lecture = _Lecture(client, db_session, API_KEY)
    await lecture.capture("Merge Sort")
    await lecture.capture("Running Time")
    assert lecture.sorter.calls == 0
    slides = (await db_session.execute(select(Slide))).scalars().all()
    assert all(slide.series_id is None for slide in slides)
