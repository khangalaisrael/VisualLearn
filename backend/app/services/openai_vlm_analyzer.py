"""OpenAIVLMAnalyzer — a SlideAnalyzer implementation backed by OpenAI.

Selected as the default active analyzer per
docs/adr/ADR-009-openai-as-active-vlm-provider.md — a practical
API-access/billing decision, not a reversal of ADR-004's VLM-first
architecture (a single multimodal call with structured outputs, replacing
separate OCR / math-OCR / layout-detection stages). This class implements
that same architecture against a different provider, sharing the same
prompt (prompts/analysis.v3.md) and output schema
(app/services/vlm_output.py) as ClaudeVLMAnalyzer.
"""

import base64
import json

import openai

from app.core.prompt_loader import load_prompt
from app.services.slide_analyzer import AnalysisResult
from app.services.vlm_output import GRAPH_LOCALIZATION_SCHEMA, OUTPUT_SCHEMA, detect_media_type, parse_analysis_payload

_DEFAULT_MODEL = "gpt-4o"


class OpenAIVLMAnalyzer:
    """SlideAnalyzer backed by a single OpenAI vision call with structured outputs."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = _DEFAULT_MODEL,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("OpenAIVLMAnalyzer requires either api_key or an injected client")
            client = openai.AsyncOpenAI(api_key=api_key)
        self._client = client
        self.model_name = model
        self._system_prompt = load_prompt("analysis.v3")
        self._graph_localization_prompt = load_prompt("graph_localization.v1")

    async def analyze(self, image_bytes: bytes) -> AnalysisResult:
        media_type = detect_media_type(image_bytes)
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")

        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this slide."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                        },
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "slide_analysis",
                    "schema": OUTPUT_SCHEMA,
                    "strict": True,
                },
            },
        )

        message = response.choices[0].message
        if message.refusal:
            raise RuntimeError(f"OpenAI declined to analyze slide: {message.refusal}")

        payload = json.loads(message.content)
        return await parse_analysis_payload(payload, image_bytes, self._locate_graph_nodes)

    async def _locate_graph_nodes(self, crop_bytes: bytes) -> dict:
        """The second, focused pass (docs/adr/ADR-010) — given just a crop
        of one graph object, locate its nodes/weight labels within that
        crop's own frame. See vlm_output.py's module docstring for why
        this pass exists separately from the main analyze() call."""
        media_type = detect_media_type(crop_bytes)
        image_b64 = base64.standard_b64encode(crop_bytes).decode("ascii")

        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self._graph_localization_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Locate the nodes and weight labels in this diagram."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                        },
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "graph_localization",
                    "schema": GRAPH_LOCALIZATION_SCHEMA,
                    "strict": True,
                },
            },
        )
        message = response.choices[0].message
        if message.refusal:
            raise RuntimeError(f"OpenAI declined to localize graph nodes: {message.refusal}")
        return json.loads(message.content)
