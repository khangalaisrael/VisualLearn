"""One long answer from the model, received as a stream.

A long quiz or a guide to a long series needs a large answer allowance, and
the SDK refuses a plain request whose allowance could take over ten minutes
to fill. Streaming has no such limit. Callers still get one complete message.
"""

from typing import Any

import anthropic


async def final_message(client: anthropic.AsyncAnthropic, **request: Any) -> Any:
    async with client.messages.stream(**request) as stream:
        return await stream.get_final_message()
