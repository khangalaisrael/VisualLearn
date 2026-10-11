"""StudyAidGenerator: writes a study guide, a cheat sheet or a deck of
flashcards from a series' slides (read as text, services/series_source.py).

The guide and the cheat sheet are markdown documents; flashcards come back
as structured output. One model call each.
"""

import json
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic

from app.core.prompt_loader import load_prompt
from app.services.model_call import final_message
from app.services.series_source import SeriesText, format_slides
from app.services.usage import record_response_usage

AidKind = Literal["guide", "cheatsheet", "flashcards"]

MAX_CARDS = 20
_MIN_CARDS = 8
_CARDS_PER_SLIDE = 4
# Thinking counts against max_tokens. A guide to a short series is about
# 1,500 tokens of text and it grows with the series (30 slides: 7,000 with
# thinking), so the request is streamed (services/model_call.py).
_MAX_TOKENS = 32_000

_PROMPTS: dict[AidKind, str] = {
    "guide": "study_guide.v1",
    "cheatsheet": "cheat_sheet.v1",
    "flashcards": "flashcards.v1",
}
TITLES: dict[AidKind, str] = {"guide": "study guide", "cheatsheet": "cheat sheet", "flashcards": "flashcards"}

_CARDS_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"front": {"type": "string"}, "back": {"type": "string"}},
                "required": ["front", "back"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Card:
    front: str
    back: str


@dataclass(frozen=True)
class GeneratedAid:
    """Exactly one of `markdown` (guide, cheat sheet) and `cards` (flashcards) is set."""

    title: str
    markdown: str | None = None
    cards: list[Card] | None = None


class StudyAidGenerator(Protocol):
    model_name: str

    async def generate(self, kind: AidKind, source: SeriesText) -> GeneratedAid: ...


def aid_title(kind: AidKind, source: SeriesText) -> str:
    return f"{source.title} {TITLES[kind]}"[:160]


def card_count(source: SeriesText) -> int:
    """More slides, more cards, within a range that stays a short session."""
    return max(_MIN_CARDS, min(MAX_CARDS, _CARDS_PER_SLIDE * len(source.slides)))


def parse_cards(payload: dict) -> list[Card]:
    """Keeps cards that have both sides: structured output guarantees the
    JSON shape, not that a side is non-empty."""
    cards = [
        Card(front=raw["front"].strip(), back=raw["back"].strip())
        for raw in payload["cards"]
        if raw["front"].strip() and raw["back"].strip()
    ]
    if not cards:
        raise ValueError("The model returned no usable cards")
    return cards[:MAX_CARDS]


class PlaceholderStudyAidGenerator:
    """Used when no Anthropic key is configured, and by the tests: fixed,
    obviously fake content, no model call."""

    model_name = "placeholder"

    async def generate(self, kind: AidKind, source: SeriesText) -> GeneratedAid:
        title = aid_title(kind, source)
        if kind == "flashcards":
            cards = [Card(front=f"Placeholder question {i + 1}?", back=f"Placeholder answer {i + 1}.") for i in range(card_count(source))]
            return GeneratedAid(title=title, cards=cards)
        return GeneratedAid(
            title=title,
            markdown=f"## Placeholder {TITLES[kind]}\n\nSet ANTHROPIC_API_KEY to write a real one for {source.title}.",
        )


class ClaudeStudyAidGenerator:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("ClaudeStudyAidGenerator requires either api_key or an injected client")
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self.model_name = model

    async def generate(self, kind: AidKind, source: SeriesText) -> GeneratedAid:
        request = format_slides(source)
        output_config: dict = {"effort": "medium"}
        if kind == "flashcards":
            request += f"\n\nWrite {card_count(source)} cards."
            output_config["format"] = {"type": "json_schema", "schema": _CARDS_SCHEMA}

        response = await final_message(
            self._client,
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=load_prompt(_PROMPTS[kind]),
            output_config=output_config,
            messages=[{"role": "user", "content": request}],
        )
        record_response_usage(response, "input_tokens", "output_tokens")
        # A cut-off or declined answer is not a study aid: fail rather than save half of one.
        if response.stop_reason != "end_turn":
            raise ValueError(f"The model stopped early ({response.stop_reason})")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise ValueError("The model returned no text")

        title = aid_title(kind, source)
        if kind == "flashcards":
            return GeneratedAid(title=title, cards=parse_cards(json.loads(text)))
        return GeneratedAid(title=title, markdown=text)
