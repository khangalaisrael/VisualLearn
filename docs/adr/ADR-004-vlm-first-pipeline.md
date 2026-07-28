# ADR-004: VLM-First Analysis Pipeline (User Decision)

## Status
Accepted — confirmed directly by the project owner during architecture planning. **Amended by [ADR-009](./ADR-009-openai-as-active-vlm-provider.md):** the concrete provider actually selected by default is now OpenAI, not Claude — a billing/access decision. The core decision below (single multimodal call + structured outputs, built behind a swappable `SlideAnalyzer` protocol) is unchanged; `ClaudeVLMAnalyzer` remains a fully supported implementation of it.

## Context
The original specs (PRD, MVP Build Spec) describe a multi-stage pipeline: screenshot ingestion → layout detection → OCR → math OCR → figure classification → vision analysis → object extraction → embedding generation. Each stage was implicitly a separate specialized model/engine (an OCR engine, a math OCR engine, a layout detector, a vision-language model). Modern multimodal models (Claude with vision + structured outputs) can perform layout detection, text OCR, LaTeX transcription, and figure/diagram understanding in a single call, returning a schema-constrained JSON result.

The project owner was asked to choose between (a) a VLM-first pipeline, (b) a fully specialized multi-engine pipeline as originally scoped, or (c) a hybrid running both in parallel from day one, and chose (a).

## Decision
Use a single Claude vision call with structured outputs (`output_config.format`) as the MVP's entire slide-analysis pipeline, producing layout, OCR text, LaTeX, and figure/diagram summaries together. Keep every analysis stage behind the `SlideAnalyzer` protocol ([ARCHITECTURE.md](../ARCHITECTURE.md) §4.1) so specialized engines can be introduced later without touching any caller.

## Rationale
- **Fastest path to a working, demoable MVP** — one integration (Claude API) instead of four-plus (layout model, OCR engine, math-OCR engine, vision model), each with its own dependency footprint, hosting/GPU needs, and failure modes.
- **Structured outputs eliminate the "merge results from N engines" problem entirely** — a single schema-constrained response is directly persistable as `objects` rows ([DATA_MODEL.md](../DATA_MODEL.md)), with no cross-engine coordinate-alignment or type-reconciliation logic to build and maintain.
- **Reversibility is designed in, not assumed.** Because every caller depends on the `SlideAnalyzer` protocol rather than "Claude" directly, replacing this decision later — e.g. introducing a dedicated math-OCR engine for higher LaTeX fidelity, or a specialized layout detector for very dense slides — is an additive change (a new class implementing the protocol, a config flag), not a rewrite of `api/` or the retrieval/chat layers.
- **Cost is a known, monitored trade-off**, not an oversight: per-slide vision calls are more expensive per call than a self-hosted OCR engine at scale, mitigated by the image-hash cache ([ARCHITECTURE.md](../ARCHITECTURE.md) §5) and the Batch API option for bulk indexing.

## Alternatives Considered
- **Specialized pipeline from day one** (PaddleOCR/Tesseract for text, Pix2Text/MathPix for LaTeX, a dedicated layout-detection model, VLM only for diagrams). More control and cheaper per-slide at scale, but 3–4x the engineering effort before any working demo, heavier local/GPU dependencies, and a much harder integration surface (merging four engines' outputs into one coherent object list). Rejected for the MVP; remains a valid future direction if per-slide cost or specific-engine accuracy becomes a real bottleneck.
- **Hybrid from the start** (local OCR + VLM in parallel, merged). Best theoretical accuracy but pays both engineering and API cost simultaneously, and merge-logic complexity is the hardest part of the specialized pipeline without deferring any of that cost. Rejected as premature before the MVP proves which specific stages, if any, actually need a specialized replacement.

## Consequences
- The MVP's per-slide cost profile is dominated by Claude API vision calls; the caching strategy in [ARCHITECTURE.md](../ARCHITECTURE.md) §5 and prompt design in [PROMPTS.md](../PROMPTS.md) §2 are load-bearing for cost control, not optional polish.
- LaTeX transcription fidelity is bounded by the VLM's native math-reading ability rather than a purpose-built math-OCR engine; if this proves insufficient in testing (Milestone 2, [ROADMAP.md](../ROADMAP.md)), introducing a dedicated `MathOCRService` behind the same protocol is the planned escape hatch.
- Bounding-box precision depends on the VLM's spatial grounding rather than a dedicated layout detector; this should be explicitly validated against the <8s / accuracy targets during Milestone 2 testing before committing further.
