"""CodeFixer: turns a student's code into a complete program that runs.

Code from a slide is usually a fragment (a function with no main), and a
program that failed needs its mistake found. One model call returns the whole
program and a short note on what was changed. The result is not run here: the
panel runs it through the code runner, so the student sees for themselves
whether it works.
"""

import json
from dataclasses import dataclass
from typing import Protocol

import anthropic

from app.core.prompt_loader import load_prompt
from app.services.code_runner import MAX_CODE_CHARS, Language
from app.services.usage import record_response_usage

# Thinking counts against max_tokens; a program for the runner is short.
_MAX_TOKENS = 8_000
# How much of a failed run is shown to the model: the start of a compiler's
# output names the first error, which is the one that matters.
MAX_ERROR_CHARS = 4_000
_MAX_NOTE_CHARS = 400

_NAMES: dict[Language, str] = {"haskell": "Haskell", "java": "Java", "cpp": "C++", "python": "Python"}

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}, "note": {"type": "string"}},
    "required": ["code", "note"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class FixedCode:
    code: str
    # What was added or changed, in a sentence or two.
    note: str


class CodeFixer(Protocol):
    model_name: str

    async def make_runnable(self, language: Language, code: str, stdin: str, last_run: str) -> FixedCode: ...


def format_request(language: Language, code: str, stdin: str, last_run: str) -> str:
    parts = [f"Language: {_NAMES[language]}", f"<code>\n{code}\n</code>"]
    if stdin.strip():
        parts.append(f"<input_the_program_reads>\n{stdin}\n</input_the_program_reads>")
    if last_run.strip():
        parts.append(f"<last_run>\n{last_run[:MAX_ERROR_CHARS]}\n</last_run>")
    return "\n\n".join(parts)


def parse_fix(payload: dict) -> FixedCode:
    code = str(payload.get("code") or "").strip("\n")
    if not code.strip():
        raise ValueError("The model returned no code")
    if len(code) > MAX_CODE_CHARS:
        raise ValueError("The model returned more code than the runner accepts")
    note = " ".join(str(payload.get("note") or "").split())[:_MAX_NOTE_CHARS]
    return FixedCode(code=code + "\n", note=note)


class ClaudeCodeFixer:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("ClaudeCodeFixer requires either api_key or an injected client")
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self.model_name = model

    async def make_runnable(self, language: Language, code: str, stdin: str, last_run: str) -> FixedCode:
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=load_prompt("code_runnable.v1"),
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": format_request(language, code, stdin, last_run)}],
        )
        record_response_usage(response, "input_tokens", "output_tokens")
        if response.stop_reason == "max_tokens":
            raise ValueError("The model ran out of room before finishing the program")
        return parse_fix(json.loads(next(block for block in response.content if block.type == "text").text))


class PlaceholderCodeFixer:
    """Used when no Anthropic key is configured, and by the tests: the code comes back unchanged."""

    model_name = "placeholder"

    async def make_runnable(self, language: Language, code: str, stdin: str, last_run: str) -> FixedCode:
        return FixedCode(code=code, note="Placeholder: set ANTHROPIC_API_KEY to have code completed.")
