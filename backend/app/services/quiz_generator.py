"""QuizGenerator: writes a multiple-choice quiz from a series' slides.

One text-only call with structured output. The slides are sent as their
already-extracted text (capped per slide and in number), never as images, so
a quiz costs a few thousand input tokens whatever the series' size.
"""

import json
from dataclasses import dataclass, field
from typing import Protocol

import anthropic

from app.core.prompt_loader import load_prompt
from app.services.usage import record_response_usage

OPTION_COUNT = 4
# Thinking counts against max_tokens; ten questions are about 2,500 tokens.
_MAX_TOKENS = 12_000

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


@dataclass(frozen=True)
class QuizSource:
    """A series as the generator reads it. `slides` and `practice` are slide
    texts; a question's `source_slide` is a 1-based position in `slides`."""

    category: str
    title: str
    slides: list[str]
    practice: list[str] = field(default_factory=list)


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

    async def generate(self, source: QuizSource, count: int) -> GeneratedQuiz: ...


class PlaceholderQuizGenerator:
    """Used when no Anthropic key is configured, and by the tests: fixed,
    obviously fake questions, one per slide in turn, no model call."""

    model_name = "placeholder"

    async def generate(self, source: QuizSource, count: int) -> GeneratedQuiz:
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


def format_source(source: QuizSource, count: int) -> str:
    slides = "\n\n".join(f"[Slide {i}]\n{text}" for i, text in enumerate(source.slides, start=1))
    practice = (
        "\n\n<practice_questions_from_the_course>\n" + "\n\n".join(source.practice) + "\n</practice_questions_from_the_course>"
        if source.practice
        else ""
    )
    return (
        f"Series: {source.title} ({source.category})\n\n<slides>\n{slides}\n</slides>{practice}\n\n"
        f"Write {count} questions."
    )


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

    async def generate(self, source: QuizSource, count: int) -> GeneratedQuiz:
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=self._system_prompt,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": format_source(source, count)}],
        )
        record_response_usage(response, "input_tokens", "output_tokens")
        payload = json.loads(next(block for block in response.content if block.type == "text").text)
        return parse_quiz(payload, source, count)
