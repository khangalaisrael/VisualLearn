"""Unit tests for OpenAIChatService / ClaudeChatService. Never call a real
provider API — a fake client is injected instead (see the `client=`
constructor parameter, mirroring tests/backend/test_openai_vlm_analyzer.py).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.claude_chat_service import ClaudeChatService
from app.services.openai_chat_service import OpenAIChatService


class _FakeOpenAIStream:
    """Async-iterable stand-in for the object `client.chat.completions.create`
    returns when `stream=True` — yields delta chunks, then a final
    usage-only chunk (`choices=[]`), matching real OpenAI streaming shape
    when `stream_options={"include_usage": True}` is requested."""

    def __init__(self, deltas: list[str], usage: SimpleNamespace) -> None:
        self._deltas = deltas
        self._usage = usage

    def __aiter__(self):
        return self._generate()

    async def _generate(self):
        for text in self._deltas:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))], usage=None)
        yield SimpleNamespace(choices=[], usage=self._usage)


async def test_openai_chat_service_streams_deltas_and_usage() -> None:
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = _FakeOpenAIStream(
        ["Hello", ", ", "world!"],
        SimpleNamespace(prompt_tokens=42, completion_tokens=7),
    )

    service = OpenAIChatService(client=fake_client, model="gpt-4o")
    chunks = [c async for c in service.stream_chat(system_prompt="be helpful", message="hi", effort="low")]

    deltas = [c.delta for c in chunks if not c.done]
    assert deltas == ["Hello", ", ", "world!"]
    final = next(c for c in chunks if c.done)
    assert final.usage is not None
    assert final.usage.input_tokens == 42
    assert final.usage.output_tokens == 7
    assert final.usage.cache_read_input_tokens == 0


async def test_openai_chat_service_sends_correct_request_shape() -> None:
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = _FakeOpenAIStream([], SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    service = OpenAIChatService(client=fake_client, model="gpt-4o")
    async for _ in service.stream_chat(system_prompt="persona+context", message="hi", effort="medium"):
        pass

    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}
    assert kwargs["messages"][0] == {"role": "system", "content": "persona+context"}
    assert kwargs["messages"][1] == {"role": "user", "content": "hi"}


async def test_openai_chat_service_includes_prior_turns_in_request() -> None:
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = _FakeOpenAIStream([], SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    service = OpenAIChatService(client=fake_client, model="gpt-4o")
    history = [("user", "What is Big-O?"), ("assistant", "It describes worst-case growth.")]
    async for _ in service.stream_chat(system_prompt="persona+context", message="Can you give an example?", effort="medium", history=history):
        pass

    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["messages"] == [
        {"role": "system", "content": "persona+context"},
        {"role": "user", "content": "What is Big-O?"},
        {"role": "assistant", "content": "It describes worst-case growth."},
        {"role": "user", "content": "Can you give an example?"},
    ]


def test_openai_chat_service_constructor_requires_api_key_or_client() -> None:
    try:
        OpenAIChatService()
    except ValueError as exc:
        assert "api_key or an injected client" in str(exc)
    else:
        raise AssertionError("expected ValueError when neither api_key nor client is provided")


class _FakeClaudeStream:
    """Async-context-manager stand-in for `client.messages.stream(...)` —
    exposes `.text_stream` (async iterable of str deltas) and
    `get_final_message()` (matching the real Anthropic streaming helper's
    shape) rather than a raw chunk-by-chunk event stream."""

    def __init__(self, deltas: list[str], usage: SimpleNamespace) -> None:
        self._deltas = deltas
        self._usage = usage

    async def __aenter__(self) -> "_FakeClaudeStream":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    @property
    def text_stream(self):
        return self._generate()

    async def _generate(self):
        for text in self._deltas:
            yield text

    async def get_final_message(self) -> SimpleNamespace:
        return SimpleNamespace(usage=self._usage)


async def test_claude_chat_service_streams_deltas_and_usage() -> None:
    fake_client = AsyncMock()
    fake_client.messages.stream = lambda **kwargs: _FakeClaudeStream(
        ["Hi", " there"], SimpleNamespace(input_tokens=10, output_tokens=3, cache_read_input_tokens=5)
    )

    service = ClaudeChatService(client=fake_client, model="claude-opus-4-8")
    chunks = [c async for c in service.stream_chat(system_prompt="be helpful", message="hi", effort="low")]

    deltas = [c.delta for c in chunks if not c.done]
    assert deltas == ["Hi", " there"]
    final = next(c for c in chunks if c.done)
    assert final.usage is not None
    assert final.usage.input_tokens == 10
    assert final.usage.output_tokens == 3
    assert final.usage.cache_read_input_tokens == 5


async def test_claude_chat_service_includes_prior_turns_in_request() -> None:
    fake_client = AsyncMock()
    captured_kwargs: dict = {}

    def _fake_stream(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeClaudeStream([], SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0))

    fake_client.messages.stream = _fake_stream

    service = ClaudeChatService(client=fake_client, model="claude-opus-4-8")
    history = [("user", "What is Big-O?"), ("assistant", "It describes worst-case growth.")]
    async for _ in service.stream_chat(
        system_prompt="persona+context", message="Can you give an example?", effort="low", history=history
    ):
        pass

    assert captured_kwargs["messages"] == [
        {"role": "user", "content": "What is Big-O?"},
        {"role": "assistant", "content": "It describes worst-case growth."},
        {"role": "user", "content": "Can you give an example?"},
    ]


def test_claude_chat_service_constructor_requires_api_key_or_client() -> None:
    try:
        ClaudeChatService()
    except ValueError as exc:
        assert "api_key or an injected client" in str(exc)
    else:
        raise AssertionError("expected ValueError when neither api_key nor client is provided")
