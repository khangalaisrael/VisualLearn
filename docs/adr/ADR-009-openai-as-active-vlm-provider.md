# ADR-009: OpenAI as the Active VLM Provider (Amends ADR-004)

## Status
Accepted — confirmed directly by the project owner. Amends
[ADR-004](./ADR-004-vlm-first-pipeline.md); does not replace it.

## Context
[ADR-004](./ADR-004-vlm-first-pipeline.md) chose a VLM-first analysis pipeline — a single multimodal call with structured outputs, replacing separate OCR/math-OCR/layout-detection stages — and named Claude as the concrete provider, with the explicit design goal that swapping providers later would be an additive change (a new class implementing the `SlideAnalyzer` protocol, a config flag), not a rewrite.

That design goal is exactly what got exercised here, sooner than expected: the project owner has a paid OpenAI API key but not a paid Anthropic one. The Claude API is a metered, billed service with no meaningful free tier for this kind of usage — the same as OpenAI's API — so without Anthropic billing set up, `ClaudeVLMAnalyzer` cannot actually run. This is a practical access constraint, not a reassessment of Claude's suitability for the task.

## Decision
Make `OpenAIVLMAnalyzer` (`backend/app/services/openai_vlm_analyzer.py`) the analyzer `app/api/deps.py` selects by default when both provider keys could plausibly be configured: `OPENAI_API_KEY` is checked first, `ANTHROPIC_API_KEY` second, `PlaceholderSlideAnalyzer` if neither is set.

`ClaudeVLMAnalyzer` is not deprecated or removed — it remains a fully supported, equally valid implementation of the same `SlideAnalyzer` protocol for anyone who does have Anthropic API access. Both share:
- The same prompt (`prompts/analysis.v1.md`) — plain instruction text with nothing Claude- or OpenAI-specific in it.
- The same output schema and parsing logic (`backend/app/services/vlm_output.py`), factored out specifically so the two analyzers can't silently drift apart in what shape of data they produce.

## Rationale
- **ADR-004's reversibility design worked as intended.** The `SlideAnalyzer` protocol existed precisely so a provider swap wouldn't touch `api/`, `repositories/`, `CacheService`, or any test that isn't provider-specific — and in practice, it didn't. This ADR is the proof, not a redesign.
- **Cost/access is a legitimate, common reason to pick a provider**, distinct from a quality or architecture judgment. Nothing about OpenAI's `gpt-4o` (the default model in `OpenAIVLMAnalyzer`) being used here reflects a belief that it's better or worse than Claude for STEM slide analysis — it reflects which API the project owner can currently afford to call.
- **Shared prompt and schema, not shared code, is the right amount of consolidation.** The provider-specific request/response plumbing (Anthropic's `output_config.format` vs. OpenAI's `response_format` with `json_schema` + `strict`) is different enough between the two SDKs that forcing one abstraction over both would add indirection without saving much real duplication. Extracting only the schema and parsing logic (`vlm_output.py`) captures the actual shared invariant — "both providers must produce this exact shape" — without over-abstracting the API calls themselves.

## Alternatives Considered
- **Require Anthropic access before proceeding.** Would have blocked all further slide-analysis work on the project owner setting up separate billing, for no benefit over just building the OpenAI path they can actually use today.
- **Replace ClaudeVLMAnalyzer entirely rather than adding a second implementation.** Rejected: ADR-004's decision to build behind a protocol was deliberate exactly so implementations could be added or swapped without deleting a working, tested one. Removing `ClaudeVLMAnalyzer` would have been strictly a regression in optionality for no gain.
- **One unified analyzer class with an internal `if provider == "openai"` branch.** Rejected as the same "keep services independent, no branching monoliths" reasoning behind [ADR-005](./ADR-005-modular-monolith.md) applied at a smaller scale — two small classes are easier to reason about, test, and eventually delete one of than a single class with provider-conditional internals.

## Consequences
- `app/api/deps.py`'s provider-priority order (OpenAI, then Anthropic, then placeholder) is now a real behavioral decision, not just a fallback chain — documented there and here so a future reader doesn't mistake OpenAI-first for an architectural preference.
- `docs/ARCHITECTURE.md` §4.2's model-selection guidance now spans two providers instead of one; update it alongside any future provider addition.
- Cost-control mechanisms designed in ADR-004 (image-hash cache, prompt/system-message reuse) apply identically regardless of which analyzer is active — `CacheService` and `cache_entries.model_used` are provider-agnostic by design.
- If Anthropic billing is set up later, switching back (or running both — e.g. OpenAI for cost-sensitive routes, Claude for a specific quality-sensitive one) requires only a config/env change, not new code, per the model-selection table already described in `docs/ARCHITECTURE.md` §4.2.

### Milestone 3 addendum: the same reasoning now applies to chat too

`docs/ARCHITECTURE.md` §4.2 originally scoped this decision to slide analysis alone, stating chat reasoning would still default to `claude-opus-4-8` regardless. That line predates this ADR's actual motivating fact being fully internalized for every AI-calling service: the project owner's only currently-working, paid API key is OpenAI's — the same constraint applies to `ChatService` as much as it does to `SlideAnalyzer`, and there is no reason to special-case chat back to a provider that can't actually be called.

`app/api/deps.py`'s `_build_chat_service()` therefore follows the identical OpenAI-first, then-Anthropic, then-unavailable priority order as `_build_slide_analyzer()`. `OpenAIChatService` and `ClaudeChatService` (`backend/app/services/`) share the same relationship `OpenAIVLMAnalyzer`/`ClaudeVLMAnalyzer` do: same `ChatService` protocol, same prompt files per query mode (`prompts/chat_figure.v1.md`, `prompts/chat_slide.v1.md`), different provider-specific request/streaming plumbing. Unlike slide analysis, chat has no meaningful placeholder implementation — a canned response would actively mislead a student asking a real question — so `_build_chat_service()` returns `None` when neither key is set, and `POST /chat` answers `503` rather than serving a fake answer.

`docs/ARCHITECTURE.md` §4.2 is updated alongside this to drop the Claude-only chat default.
