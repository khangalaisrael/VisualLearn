"""ClaudeChatService — a ChatService implementation backed by Claude.

Fully supported alternative to `OpenAIChatService` for anyone with
Anthropic API access — see docs/adr/ADR-009-openai-as-active-vlm-provider.md
(extended to chat) for why OpenAI is the default active provider instead.
"""

from typing import AsyncIterator

import anthropic

from app.models.schemas import ChatUsage
from app.services.chat_service import ChatChunk, ChatEffort

_DEFAULT_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096


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

    async def stream_chat(self, *, system_prompt: str, message: str, effort: ChatEffort) -> AsyncIterator[ChatChunk]:
        async with self._client.messages.stream(
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=system_prompt,
            output_config={"effort": effort},
            messages=[{"role": "user", "content": message}],
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
                    cache_read_input_tokens=final.usage.cache_read_input_tokens or 0,
                ),
            )
