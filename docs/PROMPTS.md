# VisionLearn AI — Prompt Library

Status: Draft v1 · Companion docs: [ARCHITECTURE.md](./ARCHITECTURE.md) · [API_CONTRACT.md](./API_CONTRACT.md)

Per the Engineering Playbook's requirement to "maintain a Prompt Library," prompts are versioned artifacts (`analysis.v1`, `chat_slide.v1`, ...) so a prompt change can be A/B'd or rolled back independently of code. `analysis.v3` and `graph_localization.v1` are implemented as of Milestone 2 (`v3` per the math-notation fix below); `chat_figure.v2`/`chat_slide.v2` as of Milestone 3 (§3 below). The quiz/notes prompts remain design-time sketches until their milestones land.

## 1. Conventions

- **Data vs. instructions.** Anything extracted from a slide (OCR text, prior chat turns quoting slide content) is passed as *data* inside clearly delimited blocks, never concatenated into the instruction text. This is a prompt-injection defense: a slide that contains text like "ignore previous instructions" must not be able to steer the model.
- **Model.** All prompts below default to `claude-opus-4-8` (see the model-selection table in [ARCHITECTURE.md](./ARCHITECTURE.md) §4.2). Adaptive thinking stays on; `effort` is tuned per prompt as noted.
- **Structured outputs over prefill.** Every prompt that needs a specific shape back uses `output_config.format` (JSON Schema), not assistant-message prefilling — this is required behavior on current Claude models, not a style preference.
- **Versioning.** File naming: `{purpose}.v{n}.md` under the top-level `prompts/` directory, loaded by `backend/app/core/prompt_loader.py`.

## 2. Slide Analysis Prompt (`analysis.v3`)

Used by both `OpenAIVLMAnalyzer` (default, see [ADR-009](./adr/ADR-009-openai-as-active-vlm-provider.md)) and `ClaudeVLMAnalyzer` (see [ARCHITECTURE.md](./ARCHITECTURE.md) §4.1–4.2) — one call replaces the separate OCR / Math OCR / layout-detection / figure-classification stages from the original spec, regardless of which provider is active.

**System prompt:** [`prompts/analysis.v3.md`](../prompts/analysis.v3.md) — loaded verbatim as the `system` message/parameter by both analyzers. Provider-agnostic on purpose: plain instruction text, nothing Claude- or OpenAI-specific in it. `v1`/`v2` (unchanged) remain in the repo per the versioning convention below — this is an additive new version, not an in-place edit.

**`v3` addition:** `v2` scoped LaTeX formatting exclusively to the `latex` field on `equation`-type objects, so math notation embedded in a `diagram`/`paragraph`/`table` object's `extracted_text` or `summary` (e.g. inequalities, subscripts, Big-O notation) was transcribed as raw ASCII text instead of typeset LaTeX. `v3` adds a "Math notation formatting" section instructing the model to wrap inline math anywhere it appears — not just in dedicated equation objects — in `$...$` delimiters, with worked examples. The extension's `MathText` component (`extension/src/sidepanel/components/MathText.tsx`) already recognized these delimiters everywhere; it just had nothing to render before this fix.

**Output constraint:** each provider's structured-outputs feature (Anthropic's `output_config.format`, OpenAI's `response_format` with `json_schema` + `strict`) is given the same JSON Schema for `{"summary": str, "objects": [SlideObject, ...]}`, defined once in `backend/app/services/vlm_output.py` rather than derived from `SlideObject` (see [API_CONTRACT.md](./API_CONTRACT.md) §2 for that Pydantic model). Deliberate differences from a literal `SlideObject` mirror:
- **`id` is not requested from the model.** Assigning stable unique identifiers is a server-side concern; the shared parsing logic generates a UUID per object after parsing the response instead of trusting the model to invent non-colliding ids.
- **`confidence` has no `minimum`/`maximum` in the schema** (neither provider's structured-outputs subset reliably supports numeric constraints). The shared parsing logic clamps the returned value to `[0.0, 1.0]` in Python instead.
- **`graph_structure` isn't requested from the model at all** ([ADR-010](./adr/ADR-010-hybrid-graph-structure-extraction.md)). This pass's own `graph_nodes`/`graph_weight_labels` are used only as a trigger signal ("this object is a graph — run the second localization pass"), not as positions — see §2b below for why, and connectivity is never asked of any VLM pass; it's computed by `backend/app/services/graph_topology.py` via classical CV.

**User content:** the slide image (vision block, base64) plus a fixed instruction text ("Analyze this slide."). The PRD's presentation-running-topic context (to improve figure/diagram interpretation using prior slide summaries) is not implemented yet — deferred until Milestone 4's retrieval infrastructure exists to supply it cheaply, rather than threading ad hoc context through the analysis path now.

**Effort:** `medium` — analysis is high-volume and latency-sensitive (<8s target); most single-slide layouts don't need `high`/`xhigh` reasoning depth. Thinking is left at its default (off) for the same reason.

## 2b. Graph Localization Prompt (`graph_localization.v1`) — second pass for graph objects

**System prompt:** [`prompts/graph_localization.v1.md`](../prompts/graph_localization.v1.md). Used only when §2's pass reports non-null `graph_nodes` for some object — a second, focused call sent *only* for that object, not for the whole slide.

**Why a second call:** live testing against real coursework slides found the first pass's node-position accuracy degraded badly when a small graph diagram had to be localized within an entire busy slide — errors bad enough to land the reported position outside the diagram entirely, not just the smaller (~40-160px) error a single-slide pass otherwise has. The fix is architectural, not a prompt tweak: `backend/app/services/graph_topology.py`'s `crop_object_region` crops the original image down to just that object's `bounding_box` (trimmed tightly to the actual drawn content via connected-components, then upscaled), and this second prompt asks for node/weight-label positions **relative to that crop**, not the full slide — a much easier localization task once the diagram fills most of the frame and nothing else is competing for the model's spatial attention.

**Output constraint:** `GRAPH_LOCALIZATION_SCHEMA` in `backend/app/services/vlm_output.py` — just `graph_nodes` and `graph_weight_labels`, no `summary`/`bounding_box`/etc. (those came from pass 1 already). Connectivity and direction are still never asked of the model — both are computed by `graph_topology.py` from the crop the model was shown.

**Effort:** `medium` on OpenAI (no separate effort control), `low` on Claude — a small, focused crop is a lighter task than full-slide analysis.

## 3. Chat Prompts, by Query Mode (`chat_{mode}.v3`)

All chat prompts share a system-prompt skeleton (assistant persona: "You are VisionLearn, a STEM tutor embedded in the student's lecture view. Never fabricate content not present in the provided slide data.") and differ in the context assembled into the cached prefix.

**`v2` addition (same fix as `analysis.v3` above):** `v1` said nothing about math formatting, so streamed answers wrote math as plain ASCII (e.g. "Theta(n 2)" instead of $\Theta(n^2)$). `v2` adds an explicit instruction to wrap math notation in `$...$`/`$$...$$` LaTeX delimiters, with the same worked example as the analysis prompt.

**`v3` addition (direct user request):** `v2` said "answer using only the provided slide data... say so plainly" if it couldn't — so a follow-up that drifted even slightly off the slide's literal content got a non-answer instead of a real one. `v3` instead tells the model to prefer the slide data but fall back to its own STEM knowledge for out-of-scope questions, explicitly flagging when it does ("This isn't covered on the slide, but..."), while still never fabricating slide content that isn't in the data block. `v1`/`v2` (unchanged) remain in the repo, unused, per the versioning convention.

| Mode | Context content | Notes |
|---|---|---|
| Figure | The selected object's `bounding_box`/`extracted_text`/`latex`/`summary` + its slide's summary. | Smallest context; `effort: low`. **Implemented** ([`prompts/chat_figure.v3.md`](../prompts/chat_figure.v3.md)). |
| Slide | All objects on the current slide, ordered by reading position (approximated by `bounding_box.y` then `.x` — no explicit reading-order field exists yet). | `effort: medium`. **Implemented** ([`prompts/chat_slide.v3.md`](../prompts/chat_slide.v3.md)). |
| Presentation | Retrieved top-k objects/slide-summaries from `RetrievalService` + prior conversation turns. | `effort: high` — cross-slide synthesis benefits from deeper reasoning. **Not implemented** (M4, needs `RetrievalService`) — `POST /chat` rejects this mode with `400` for now. |
| General | No slide grounding; persona only. | Same persona, explicitly told it has no slide context this turn. **Not implemented** — rejected with `400`. |
| Auto | Backend resolves to one of the above before prompt assembly (see [ARCHITECTURE.md](./ARCHITECTURE.md) §4.3) — no separate prompt of its own. | **Not implemented** — rejected with `400`. |

**Two-provider note (Milestone 3, see [ADR-009](./adr/ADR-009-openai-as-active-vlm-provider.md)'s addendum):** both implemented modes are served by whichever of `OpenAIChatService`/`ClaudeChatService` is active (OpenAI-first, same selection order as slide analysis), sharing the prompt files above and the `ChatService` protocol — provider-specific request/streaming plumbing only, same split `vlm_output.py` draws for analysis.

**Response shape guidance (not a hard schema — chat responses are free text via streaming, but the system prompt asks for this shape):** per the Premium UI Guide's Chat UX — every answer should contain a summary, detailed explanation, related concepts, references (which objects were used), and a suggested follow-up. The extension renders `referenced_object_ids` (returned out-of-band in the SSE `done` event, see [API_CONTRACT.md](./API_CONTRACT.md) §3) as citation links back to the overlay.

**Placement for prompt caching:** system persona + retrieved/slide context go first and carry `cache_control`; the user's actual question is appended after the cache breakpoint so it never invalidates the cached prefix (see [ARCHITECTURE.md](./ARCHITECTURE.md) §5 and the caching design notes below). **Not yet applied to Figure/Slide mode** — their context is per-question, not reused across turns, so there's no stable prefix worth caching yet; this lands with Presentation-mode chat (M4), where the same retrieved context is genuinely reused across a session.

## 4. Quiz Generation Prompt (`quiz.v1`)

**System prompt (sketch):**
```
Generate {question_count} quiz questions testing understanding of the
provided STEM content. Mix question types (multiple choice, short answer)
appropriate to the material. Every question must be answerable strictly from
the provided content — do not require outside knowledge.
```

**Output constraint:** structured output matching `QuizResponse.questions` ([API_CONTRACT.md](./API_CONTRACT.md) §5), including `source_object_ids` so each question traces back to the object(s) it was derived from — required for the UI to link a question back to its slide.

## 5. Notes Generation Prompt (`notes.v1`)

**System prompt (sketch):**
```
Produce structured Markdown study notes summarizing the provided content.
Use headings per topic/slide, bullet points for key facts, and a dedicated
section for any equations (rendered as LaTeX) with a one-line explanation
of each.
```

**Output:** plain Markdown text (not JSON-schema-constrained) — notes are meant to be read/exported directly, matching `NotesResponse.content` / `format: "markdown"`.

## 6. Prompt-Caching Design Note

Every prompt in this library that includes a "context block" (analysis' running-topic note, chat's slide/presentation context) places that block **before** the per-request variable content (the question, the current slide image) and marks the last block of the stable portion with `cache_control`. This is the single rule that makes the caching strategy in [ARCHITECTURE.md](./ARCHITECTURE.md) §5 actually take effect — a prompt template that interpolates the question into the middle of the context (rather than appending it after) would silently defeat caching.

## 7. Open Items for Implementation

- Exact JSON Schemas for `output_config.format` on the analysis and quiz prompts should be written and tested against real slide screenshots before Milestone 2 (see [ROADMAP.md](./ROADMAP.md)) — this doc gives the shape, not the final schema strings.
- A held-out set of "adversarial" slides (slides containing text that looks like instructions) should be part of the test suite for the analysis prompt, to validate the data/instruction separation holds in practice.
