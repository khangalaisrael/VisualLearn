"""OpenAIChatService — a ChatService implementation backed by OpenAI.

Selected as the default active chat provider for the same reason
`OpenAIVLMAnalyzer` is (docs/adr/ADR-009-openai-as-active-vlm-provider.md,
extended to chat) — a practical API-access/billing decision, not a quality
judgment. `ClaudeChatService` remains fully supported.
"""

from typing import AsyncIterator

import openai

from app.models.schemas import ChatUsage
from app.services.chat_service import ChatChunk, ChatEffort

_DEFAULT_MODEL = "gpt-4o"


class OpenAIChatService:
    """ChatService backed by a streamed OpenAI chat-completion call."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = _DEFAULT_MODEL,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("OpenAIChatService requires either api_key or an injected client")
            client = openai.AsyncOpenAI(api_key=api_key)
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
        # OpenAI's chat-completions API has no "effort"/thinking-depth
        # control on gpt-4o (that's an Anthropic-specific adaptive-thinking
        # concept) — effort is accepted for interface parity with
        # ClaudeChatService but unused here.
        del effort

        stream = await self._client.chat.completions.create(
            model=self.model_name,
            stream=True,
            stream_options={"include_usage": True},
            messages=[
                {"role": "system", "content": system_prompt},
                *({"role": role, "content": content} for role, content in history),
                {"role": "user", "content": message},
            ],
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield ChatChunk(delta=chunk.choices[0].delta.content, done=False)
            if chunk.usage is not None:
                yield ChatChunk(
                    delta=None,
                    done=True,
                    usage=ChatUsage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                        cache_read_input_tokens=0,
                    ),
                )
