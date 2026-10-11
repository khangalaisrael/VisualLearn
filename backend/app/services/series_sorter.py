"""SeriesSorter: decides which topic series a captured slide belongs to.

A separate, text-only call rather than extra fields on the vision analysis
(services/vlm_output.py): the analysis is cached by image hash and shared by
every user, while sorting depends on one user's existing series. It reads the
slide's already-extracted text, so it costs a few hundred tokens, and the
same call can sort captures made before sorting existed.

The model also sees a few subtopics already filed in each series, and where
the student's previous capture went: slides are captured one after another
during a lecture, and without that the sorter splits one lecture into many
narrow series.

Existing series are shown to the model by position ("1", "2", ...) rather
than by id: a UUID is about 20 tokens the model would only copy back.
"""

import json
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic

from app.core.prompt_loader import load_prompt
from app.services.usage import record_response_usage

ContentKind = Literal["lecture", "practice"]

# The model sees at most this many of the user's series (most recently used first).
MAX_EXISTING_SERIES = 60
_MAX_TEXT_CHARS = 700
_MAX_CATEGORY_CHARS = 80
_MAX_TITLE_CHARS = 120
# Haiku thinks adaptively and thinking counts against max_tokens; the answer
# itself is under 100 tokens.
_MAX_TOKENS = 2000

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "series_number": {"type": ["integer", "null"]},
        "category": {"type": "string"},
        "title": {"type": "string"},
        "broader_title": {"type": "string"},
        "subtopic": {"type": "string"},
        "kind": {"type": "string", "enum": ["lecture", "practice"]},
    },
    "required": ["series_number", "category", "title", "broader_title", "subtopic", "kind"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ExistingSeries:
    category: str
    title: str
    # A few subtopics of slides already in it (newest first), to show its breadth.
    subtopics: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreviousCapture:
    """The student's capture just before this one, when it was recent."""

    # Index into the `existing` list of the series it was filed in.
    existing_index: int
    subtopic: str
    minutes_ago: int
    same_page: bool


@dataclass(frozen=True)
class SlideDigest:
    """What the sorter reads about one slide: text already extracted by the analysis."""

    page_title: str
    summary: str
    headings: list[str]
    text: str


@dataclass(frozen=True)
class SortDecision:
    # Index into the `existing` list that was passed in, or None for a new series.
    existing_index: int | None
    category: str
    title: str
    subtopic: str
    kind: ContentKind
    # Set when the slide joins an existing series whose title has become too
    # narrow for what it now holds: a wider title for that series.
    retitle: str | None = None


class SeriesSorter(Protocol):
    model_name: str

    async def sort(
        self, slide: SlideDigest, existing: list[ExistingSeries], previous: PreviousCapture | None = None
    ) -> SortDecision: ...


def _clean(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit].strip()


class PlaceholderSeriesSorter:
    """Used when no Anthropic key is configured, and by the tests. No model
    call: a series per page title, which is the grouping "Recent" had before
    sorting existed."""

    model_name = "placeholder"

    async def sort(
        self, slide: SlideDigest, existing: list[ExistingSeries], previous: PreviousCapture | None = None
    ) -> SortDecision:
        title = _clean(slide.page_title, _MAX_TITLE_CHARS) or "Untitled"
        lowered = title.lower()
        index = next((i for i, series in enumerate(existing) if series.title.lower() == lowered), None)
        return SortDecision(
            existing_index=index,
            category=existing[index].category if index is not None else "General",
            title=existing[index].title if index is not None else title,
            subtopic="",
            kind="practice" if any(word in lowered for word in ("practice", "exercise", "tutorial")) else "lecture",
        )


def _format_series(number: int, series: ExistingSeries) -> str:
    line = f"{number}. {series.category} | {series.title}"
    return f"{line} (so far: {'; '.join(series.subtopics)})" if series.subtopics else line


def _format_previous(previous: PreviousCapture | None, existing: list[ExistingSeries]) -> str:
    if previous is None or not 0 <= previous.existing_index < len(existing):
        return ""
    when = "just now" if previous.minutes_ago < 1 else f"{previous.minutes_ago} min ago"
    page = "the same page as this slide" if previous.same_page else "a different page"
    about = f', about "{previous.subtopic}"' if previous.subtopic else ""
    return (
        f"<previous_capture>\nCaptured {when} from {page}{about}. "
        f"It was filed in series {previous.existing_index + 1}.\n</previous_capture>\n\n"
    )


def _format_request(
    slide: SlideDigest, existing: list[ExistingSeries], previous: PreviousCapture | None = None
) -> str:
    listed = "\n".join(_format_series(i, s) for i, s in enumerate(existing, start=1)) or "(none yet)"
    headings = "; ".join(slide.headings) or "(none)"
    return (
        f"<existing_series>\n{listed}\n</existing_series>\n\n"
        f"{_format_previous(previous, existing)}"
        f"<slide>\nPage title: {slide.page_title or '(none)'}\nHeadings: {headings}\n"
        f"Summary: {slide.summary or '(none)'}\nText: {slide.text[:_MAX_TEXT_CHARS] or '(none)'}\n</slide>"
    )


class ClaudeSeriesSorter:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("ClaudeSeriesSorter requires either api_key or an injected client")
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self.model_name = model
        self._system_prompt = load_prompt("sort_series.v1")

    async def sort(
        self, slide: SlideDigest, existing: list[ExistingSeries], previous: PreviousCapture | None = None
    ) -> SortDecision:
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=self._system_prompt,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": _format_request(slide, existing, previous)}],
        )
        record_response_usage(response, "input_tokens", "output_tokens")
        payload = json.loads(next(block for block in response.content if block.type == "text").text)

        number = payload["series_number"]
        index = number - 1 if isinstance(number, int) and 1 <= number <= len(existing) else None
        retitle = None
        if index is not None:
            # The series' own wording wins over whatever the model repeated back.
            category, title = existing[index].category, existing[index].title
            broader = _clean(payload.get("broader_title") or "", _MAX_TITLE_CHARS)
            retitle = broader if broader and broader.lower() != title.lower() else None
        else:
            category = _clean(payload["category"], _MAX_CATEGORY_CHARS) or "General"
            title = _clean(payload["title"], _MAX_TITLE_CHARS) or _clean(slide.page_title, _MAX_TITLE_CHARS) or "Untitled"
        return SortDecision(
            existing_index=index,
            category=category,
            title=title,
            subtopic=_clean(payload["subtopic"], _MAX_TITLE_CHARS),
            kind=payload["kind"],
            retitle=retitle,
        )
