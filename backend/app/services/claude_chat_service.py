"""ClaudeChatService — a ChatService implementation backed by Claude.

Fully supported alternative to `OpenAIChatService` for anyone with
Anthropic API access — see docs/adr/ADR-009-openai-as-active-vlm-provider.md
(extended to chat) for why OpenAI is the default active provider instead.
"""

from typing import AsyncIterator

import anthropic

from app.models.schemas import ChatUsage
from app.services.chat_service import ChatChunk, ChatEffort

_DEFAULT_MODEL = "claude-haiku-5-5"
# Headroom for adaptive thinking, which counts against max_tokens (only
# tokens actually generated are billed).
_MAX_TOKENS = 8192

# Prompt caching: the system prompt (persona plus the slide's data) is the
# same on every turn of a conversation, and each turn resends all the turns
# before it. Two breakpoints mark that shared prefix, so the next turn reads
# it back at a tenth of the input price instead of paying for it again: one
# on the system prompt, one on the last earlier turn. A prefix shorter than
# the model's minimum is simply not cached (no error), and a cache entry
# lives 5 minutes from its last use, which covers a student's follow-ups.
_CACHE = {"type": "ephemeral"}


def _request_messages(history: list[tuple[str, str]], message: str) -> list[dict]:
    """The earlier turns, then this one, with a cache breakpoint on the last
    earlier turn (the end of what the next turn will resend unchanged)."""
    messages: list[dict] = [{"role": role, "content": content} for role, content in history]
    if messages:
        last = messages[-1]
        last["content"] = [{"type": "text", "text": last["content"], "cache_control": _CACHE}]
    messages.append({"role": "user", "content": message})
    return messages


class ClaudeChatService:
    """ChatService backed by a streamed Claude message call."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = _DEFAULT_MODEL,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("ClaudeChatService requires either api_key or an injected client")
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self.model_name = model

    async def stream_chat(
        self,
        *,
        system_prompt: str,
        message: str,
        effort: ChatEffort,
        history: list[tuple[str, str]] = (),
    ) -> AsyncIterator[ChatChunk]:
        async with self._client.messages.stream(
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": system_prompt, "cache_control": _CACHE}],
            output_config={"effort": effort},
            messages=_request_messages(list(history), message),
        ) as stream:
            async for delta in stream.text_stream:
                yield ChatChunk(delta=delta, done=False)

            final = await stream.get_final_message()
            yield ChatChunk(
                delta=None,
                done=True,
                usage=ChatUsage(
                    input_tokens=final.usage.input_tokens,
                    output_tokens=final.usage.output_tokens,
                    cache_read_input_tokens=getattr(final.usage, "cache_read_input_tokens", None) or 0,
                    cache_creation_input_tokens=getattr(final.usage, "cache_creation_input_tokens", None) or 0,
                ),
            )
