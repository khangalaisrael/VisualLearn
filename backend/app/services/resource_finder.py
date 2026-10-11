"""ResourceFinder: searches the web for study resources on a series' topic.

Uses Anthropic's server-side web search tool, so the searches run on their
side and each one is billed (see `web_search_usd_per_request`). Admins only
for now (api/v1/quizzes.py).

A link is only ever returned if its exact URL appeared in a search result of
this same call. The model picks and describes resources, but a URL it writes
is not trusted: in a live test it returned a subtly altered address
(`www.dal.ca/...` for a result at `www.mscs.dal.ca/...`), and such a link
is dropped here rather than shown to a student.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

import anthropic

from app.core.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

MAX_RESOURCES = 4
_MAX_TOKENS = 6000
# A server-side search turn can pause; it is resumed at most this many times.
_MAX_CONTINUATIONS = 2
# The basic search tool works on every current model. The newer one filters
# results before they reach the context (fewer input tokens) but is not
# offered on Haiku.
_BASIC_TOOL = "web_search_20250305"
_FILTERING_TOOL = "web_search_20260209"
_FILTERING_MODEL_PREFIXES = ("claude-opus-", "claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-")

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "resources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"url": {"type": "string"}, "title": {"type": "string"}, "why": {"type": "string"}},
                "required": ["url", "title", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["resources"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Resource:
    title: str
    url: str
    why: str


@dataclass(frozen=True)
class ResearchResult:
    resources: list[Resource] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    searches: int = 0


class ResourceFinder(Protocol):
    model_name: str

    async def find(self, *, category: str, title: str, subtopics: list[str]) -> ResearchResult: ...


def search_tool_type(model: str) -> str:
    return _FILTERING_TOOL if model.startswith(_FILTERING_MODEL_PREFIXES) else _BASIC_TOOL


def _searched_urls(content: list) -> set[str]:
    """Every URL the search tool actually returned in this response."""
    urls: set[str] = set()
    for block in content:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        results = block.content
        if not isinstance(results, list):  # a search error is a single object, not a list
            continue
        urls.update(result.url for result in results if getattr(result, "url", None))
    return urls


def pick_resources(payload: dict, searched: set[str]) -> list[Resource]:
    picked: list[Resource] = []
    for raw in payload.get("resources", []):
        url = raw["url"].strip()
        if url not in searched or not url.startswith(("https://", "http://")):
            continue
        if any(existing.url == url for existing in picked):
            continue
        title = " ".join(raw["title"].split())[:200]
        if title:
            picked.append(Resource(title=title, url=url, why=" ".join(raw["why"].split())[:300]))
    return picked[:MAX_RESOURCES]


class ClaudeResourceFinder:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str,
        max_searches: int,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("ClaudeResourceFinder requires either api_key or an injected client")
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self.model_name = model
        self._max_searches = max_searches
        self._system_prompt = load_prompt("research_resources.v1")

    async def find(self, *, category: str, title: str, subtopics: list[str]) -> ResearchResult:
        points = "; ".join(subtopics) or "(none listed)"
        messages: list[dict] = [
            {"role": "user", "content": f"Topic: {title} ({category})\nPoints the slides cover: {points}"}
        ]
        searched: set[str] = set()
        input_tokens = output_tokens = searches = 0
        response = None
        for _ in range(_MAX_CONTINUATIONS + 1):
            response = await self._client.messages.create(
                model=self.model_name,
                max_tokens=_MAX_TOKENS,
                system=self._system_prompt,
                tools=[{"type": search_tool_type(self.model_name), "name": "web_search", "max_uses": self._max_searches}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
                messages=messages,
            )
            searched |= _searched_urls(response.content)
            input_tokens += response.usage.input_tokens or 0
            output_tokens += response.usage.output_tokens or 0
            searches += getattr(getattr(response.usage, "server_tool_use", None), "web_search_requests", 0) or 0
            if response.stop_reason != "pause_turn":
                break
            # Resume: send the paused turn back unchanged; no extra user message.
            messages = [messages[0], {"role": "assistant", "content": response.content}]

        resources: list[Resource] = []
        text = next((block.text for block in reversed(response.content) if block.type == "text"), None)
        if response.stop_reason == "end_turn" and text:
            try:
                resources = pick_resources(json.loads(text), searched)
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("research_unparseable_answer")
        return ResearchResult(
            resources=resources, input_tokens=input_tokens, output_tokens=output_tokens, searches=searches
        )
