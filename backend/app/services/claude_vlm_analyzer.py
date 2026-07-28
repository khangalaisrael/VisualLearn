"""ClaudeVLMAnalyzer — a SlideAnalyzer implementation backed by Claude.

Per docs/adr/ADR-004-vlm-first-pipeline.md, a single Claude vision call with
structured outputs (`output_config.format`) replaces the separate OCR /
math-OCR / layout-detection / figure-classification stages from the
original spec. See docs/PROMPTS.md §2 for the prompt design and
docs/API_CONTRACT.md §2 for the shape this feeds into.

Since docs/adr/ADR-009-openai-as-active-vlm-provider.md, `OpenAIVLMAnalyzer`
(app/services/openai_vlm_analyzer.py) is the analyzer actually selected by
default (app/api/deps.py) — this class remains available and fully
supported for anyone with Anthropic API access, sharing the same prompt and
output schema (app/services/vlm_output.py) so both stay interchangeable
behind the `SlideAnalyzer` protocol.
"""

import base64
import json

import anthropic

from app.core.prompt_loader import load_prompt
from app.services.slide_analyzer import AnalysisResult
from app.services.vlm_output import GRAPH_LOCALIZATION_SCHEMA, OUTPUT_SCHEMA, detect_media_type, parse_analysis_payload

_DEFAULT_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096


class ClaudeVLMAnalyzer:
    """SlideAnalyzer backed by a single Claude vision call with structured outputs."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = _DEFAULT_MODEL,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("ClaudeVLMAnalyzer requires either api_key or an injected client")
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self.model_name = model
        self._system_prompt = load_prompt("analysis.v3")
        self._graph_localization_prompt = load_prompt("graph_localization.v1")

    async def analyze(self, image_bytes: bytes) -> AnalysisResult:
        media_type = detect_media_type(image_bytes)
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")

        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=self._system_prompt,
            output_config={
                # Analysis is high-volume and latency-sensitive (<8s target,
                # docs/ARCHITECTURE.md §6) — "medium" per docs/PROMPTS.md §2.
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": "Analyze this slide."},
                    ],
                }
            ],
        )

        text_block = next(block for block in response.content if block.type == "text")
        payload = json.loads(text_block.text)
        return await parse_analysis_payload(payload, image_bytes, self._locate_graph_nodes)

    async def _locate_graph_nodes(self, crop_bytes: bytes) -> dict:
        """The second, focused pass (docs/adr/ADR-010) — given just a crop
        of one graph object, locate its nodes/weight labels within that
        crop's own frame. See vlm_output.py's module docstring for why
        this pass exists separately from the main analyze() call."""
        media_type = detect_media_type(crop_bytes)
        image_b64 = base64.standard_b64encode(crop_bytes).decode("ascii")

        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=_MAX_TOKENS,
            system=self._graph_localization_prompt,
            output_config={
                "effort": "low",  # small, focused crop — a lighter task than full-slide analysis
                "format": {"type": "json_schema", "schema": GRAPH_LOCALIZATION_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": "Locate the nodes and weight labels in this diagram."},
                    ],
                }
            ],
        )
        text_block = next(block for block in response.content if block.type == "text")
        return json.loads(text_block.text)
