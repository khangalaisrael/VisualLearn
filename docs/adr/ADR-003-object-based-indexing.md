# ADR-003: Object-Based Indexing (Embed Objects, Not Whole Slides)

## Status
Accepted

## Context
Retrieval needs to support Figure-mode (single diagram/equation), Slide-mode (everything on one slide), and Presentation-mode (search across a deck) queries ([ARCHITECTURE.md](../ARCHITECTURE.md) §4.3). The unit of embedding and retrieval determines what granularity of answer is possible.

## Decision
Embed and index at the **object** level (per `objects` row — title, paragraph, equation, diagram, graph, table, image) in addition to a slide-level summary embedding, rather than embedding only whole-slide summaries.

## Rationale
- **Figure-mode requires object granularity.** If only whole-slide embeddings existed, "explain this diagram" (a Figure-mode query anchored to one clicked object) would have no matching retrieval unit finer than the slide — object-level embeddings are the only way this mode's grounding is precise.
- **Better Presentation-mode recall.** A single diagram buried in a dense slide can be semantically distinct from the slide's dominant topic; embedding it separately makes it independently retrievable rather than diluted into one slide-level vector.
- **Matches the object-centric data model already required by the MVP spec** (the spec's `Object` entity — id, slide_number, type, bounding_box, extracted_text, latex, summary, embedding, confidence — already implies per-object embeddings, not per-slide).

## Alternatives Considered
- **Slide-level embeddings only.** Simpler (one embedding per slide instead of one per object plus one per slide) and cheaper, but breaks Figure-mode grounding and loses recall on dense slides. Rejected.
- **Object-level only, no slide-level summary embedding.** Would work for Figure/Presentation modes but loses a cheap, coherent "what is this slide about as a whole" retrieval unit useful for Slide-mode context assembly and for the sidebar's slide summary display. The `embeddings` table's polymorphic `(owner_type, owner_id)` design (see [DATA_MODEL.md](../DATA_MODEL.md) §3) keeps both without schema duplication, so there's no cost to keeping slide-level embeddings too.

## Consequences
- More embedding calls per slide (one per object plus one for the slide summary) than a naive one-embedding-per-slide design — a minor, acceptable cost increase given `EmbeddingService`'s provider is separate from the (more expensive) vision analysis call.
- The `embeddings` table's polymorphic ownership column requires care in `RetrievalService` queries to filter by `owner_type` appropriately per query mode.
