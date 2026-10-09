"""ChatService protocol (docs/adr/ADR-004's pattern, applied to chat) —
`OpenAIChatService` / `ClaudeChatService` implement this so
`api/v1/chat.py` never depends on which provider is active, only on this
protocol (see `api/deps.py` for the same OpenAI-first selection order
already used for `SlideAnalyzer`, extended to chat).

Context assembly (loading the right prompt file for Figure vs. Slide mode,
appending the slide/object data block) is the router's job, not this
service's — `stream_chat` takes an already-fully-assembled `system_prompt`
string, so the provider-specific classes only own the API call and
streaming, the same division `vlm_output.py` draws between shared logic
and per-provider plumbing for slide analysis.
"""

from dataclasses import dataclass
from typing import AsyncIterator, Literal, Protocol

from app.models.schemas import ChatUsage

ChatEffort = Literal["low", "medium"]


@dataclass(frozen=True)
class ChatChunk:
    """One step of a streamed chat response. Either a text delta (`done`
    False, `usage` None) or the final chunk (`done` True, `delta` None,
    `usage` populated) — never both at once."""

    delta: str | None
    done: bool
    usage: ChatUsage | None = None


class ChatService(Protocol):
    model_name: str

    def stream_chat(
        self,
        *,
        system_prompt: str,
        message: str,
        effort: ChatEffort,
        history: list[tuple[str, str]] = (),
    ) -> AsyncIterator[ChatChunk]: ...
