"""QuizGenerator: writes a multiple-choice quiz from a series' slides.

One text-only call with structured output. The slides are sent as their
already-extracted text (capped per slide and in number), never as images, so
a quiz costs a few thousand input tokens whatever the series' size.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import anthropic

from app.core.prompt_loader import load_prompt
from app.services.model_call import final_message
from app.services.series_source import SeriesText, format_slides
from app.services.usage import record_response_usage

OPTION_COUNT = 4
# Thinking counts against max_tokens: twenty questions measured at up to
# 17,000 tokens with it, so the request is streamed (services/model_call.py).
_MAX_TOKENS = 32_000
# Earlier questions shown to the model so a new quiz asks something else:
# the most recent ones, each cut short (only the gist is needed).
MAX_ASKED = 60
_ASKED_CHARS = 200

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_index": {"type": "integer"},
                    "explanation": {"type": "string"},
                    "source_slide": {"type": "integer"},
                },
                "required": ["question", "options", "correct_index", "explanation", "source_slide"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "questions"],
    "additionalProperties": False,
}


# A series as the generator reads it; a question's `source_slide` is a
# 1-based position in `slides`.
QuizSource = SeriesText


@dataclass(frozen=True)
class GeneratedQuestion:
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    # 0-based index into QuizSource.slides, or None when the model named no valid slide.
    source_index: int | None


@dataclass(frozen=True)
class GeneratedQuiz:
    title: str
    questions: list[GeneratedQuestion]


class QuizGenerator(Protocol):
    model_name: str

    async def generate(self, source: QuizSource, count: int, asked: Sequence[str] = ()) -> GeneratedQuiz: ...


class PlaceholderQuizGenerator:
    """Used when no Anthropic key is configured, and by the tests: fixed,
    obviously fake questions, one per slide in turn, no model call."""

    model_name = "placeholder"

    async def generate(self, source: QuizSource, count: int, asked: Sequence[str] = ()) -> GeneratedQuiz:
        questions = [
            GeneratedQuestion(
                question=f"Placeholder question {i + 1} about {source.title}?",
                options=["First option", "Second option", "Third option", "Fourth option"],
                correct_index=i % OPTION_COUNT,
                explanation="Placeholder explanation: set ANTHROPIC_API_KEY to generate real quizzes.",
                source_index=i % len(source.slides) if source.slides else None,
            )
            for i in range(count)
        ]
        return GeneratedQuiz(title=f"{source.title} quiz", questions=questions)


def format_source(source: QuizSource, count: int, asked: Sequence[str] = ()) -> str:
    earlier = [" ".join(question.split())[:_ASKED_CHARS] for question in asked[-MAX_ASKED:]]
    block = (
        "\n\n<already_asked>\n" + "\n".join(f"- {question}" for question in earlier) + "\n</already_asked>"
        if earlier
        else ""
    )
    return f"{format_slides(source)}{block}\n\nWrite {count} questions."


def parse_quiz(payload: dict, source: QuizSource, count: int) -> GeneratedQuiz:
    """Keeps only well-formed questions (four options, a valid correct index):
    structured output guarantees the JSON shape, not these counts."""
    questions: list[GeneratedQuestion] = []
    for raw in payload["questions"]:
        options = [str(option).strip() for option in raw["options"]]
        if len(options) != OPTION_COUNT or not 0 <= raw["correct_index"] < OPTION_COUNT or not raw["question"].strip():
            continue
        slide_number = raw["source_slide"]
        questions.append(
            GeneratedQuestion(
                question=raw["question"].strip(),
                options=options,
                correct_index=raw["correct_index"],
                explanation=raw["explanation"].strip(),
                source_index=slide_number - 1 if 1 <= slide_number <= len(source.slides) else None,
            )
        )
    if not questions:
        raise ValueError("The model returned no usable questions")
    return GeneratedQuiz(title=" ".join(payload["title"].split())[:160] or f"{source.title} quiz", questions=questions[:count])


class ClaudeQuizGenerator:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("ClaudeQuizGenerator requires either api_key or an injected client")
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self.model_name = model
        self._system_prompt = load_prompt("quiz_generate.v1")

    async def generate(self, source: QuizSource, count: int, asked: Sequence[str] = ()) -> GeneratedQuiz:
        response = await final_message(
            self._client,
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=self._system_prompt,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": format_source(source, count, asked)}],
        )
        record_response_usage(response, "input_tokens", "output_tokens")
        # A cut-off answer is broken JSON: say what happened instead.
        if response.stop_reason == "max_tokens":
            raise ValueError("The model ran out of room before finishing the quiz")
        payload = json.loads(next(block for block in response.content if block.type == "text").text)
        return parse_quiz(payload, source, count)
