# ADR-006: Voyage AI as Embedding Provider, with Local Fallback

## Status
Accepted

## Context
Retrieval ([ADR-003](./ADR-003-object-based-indexing.md)) requires turning object/slide text into vectors. Anthropic's Claude API does not offer an embeddings endpoint, so this must be a separate provider from the one used for vision analysis and chat ([ADR-004](./ADR-004-vlm-first-pipeline.md)).

## Decision
Use Voyage AI (`voyage-3` family) as the default embedding provider, with a local `sentence-transformers` model as a configurable fallback, both behind the `EmbeddingService` protocol ([ARCHITECTURE.md](../ARCHITECTURE.md) §4.1).

## Rationale
- **Quality and Anthropic ecosystem alignment.** Voyage AI is Anthropic's recommended embedding partner and its models are tuned for retrieval quality on the kind of technical/academic text this product indexes.
- **Local fallback removes a hard external dependency.** A single-user, local-first tool ([ADR-007](./ADR-007-local-first-deployment.md)) should be able to run indexing without a second paid API key if the user only has an Anthropic key — a local `sentence-transformers` model (e.g. an MiniLM/BGE-class model) covers that case, at some quality cost, purely via config (`provider` field on `embeddings`, see [DATA_MODEL.md](../DATA_MODEL.md)).
- **Kept behind a protocol, like every other AI-facing capability**, so the provider choice is a configuration decision, not an architectural one baked into callers.

## Alternatives Considered
- **OpenAI embeddings.** Well-established and high quality, but introduces a third AI vendor (alongside Anthropic and, potentially, Voyage) for no clear advantage over Voyage's retrieval-tuned models; adds an extra API key to manage for a local-first tool aiming to minimize external dependencies.
- **Local-only (no cloud embedding provider at all).** Simplest dependency story and works fully offline, but meaningfully lower retrieval quality than a purpose-built API model — acceptable as a fallback, not as the default, given retrieval quality directly affects Presentation-mode answer correctness.

## Consequences
- Embedding dimension is fixed by the chosen Voyage model at first migration time ([DATA_MODEL.md](../DATA_MODEL.md) §5); switching providers later requires a re-embed of existing data, not a live schema change.
- `EmbeddingService` implementations must agree on dimension per `provider` value, or the `embeddings` table needs a per-row dimension check — a detail to resolve in the Milestone 4 implementation ([ROADMAP.md](../ROADMAP.md)).
