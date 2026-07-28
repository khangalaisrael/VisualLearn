# VisionLearn AI — Roadmap

Status: Draft v1 · Companion docs: [ARCHITECTURE.md](./ARCHITECTURE.md) · [DATA_MODEL.md](./DATA_MODEL.md) · [API_CONTRACT.md](./API_CONTRACT.md)

The five spec milestones (`VisionLearn_MVP_Build_Spec.md`) mapped onto the Engineering Playbook's 12-week schedule as vertical slices — every sprint ends with working, demoable software, per the playbook's guiding principles. Each milestone below is 2 weeks and follows the playbook's sprint lifecycle: Plan → Design → Implement → Test → Demo → Retrospective.

## Milestone 1 — Foundation (Weeks 1–2)

**Goal:** repo, extension shell, and backend shell talking to each other end-to-end with a placeholder response.

- Repo scaffold per the folder structure in the root [README.md](../README.md).
- Chrome extension (MV3): manifest, content script stub, service worker, side panel registration.
- FastAPI backend: `api`/`services`/`repositories`/`models`/`db`/`core` skeleton, `GET /health`, Docker Compose (FastAPI + Postgres/pgvector + Redis).
- `POST /slides/analyze` wired end-to-end but returning a hardcoded placeholder object (no Claude call yet) — proves the capture → upload → response → sidebar-render path works.
- **Demo:** open a slide in the browser, see a placeholder analysis appear in the side panel.
- **Traces to:** MVP spec success criteria "Detect current slide," "Capture visible slide" (partially — placeholder analysis only).

## Milestone 2 — Real Analysis (Weeks 3–5)

**Goal:** the VLM-first pipeline is live; slides are actually understood.

- `SlideAnalyzer` protocol + `ClaudeVLMAnalyzer` implementation (see [ARCHITECTURE.md](./ARCHITECTURE.md) §4.1, [PROMPTS.md](./PROMPTS.md) §2).
- `analysis.v1` prompt with structured-output JSON Schema, tested against a representative slide set (text, equations, diagrams, tables).
- Analysis cache (Redis + `cache_entries`, image-hash keyed).
- Sidebar: Ask/Concepts/Notes/Quiz tab shells (non-functional except Ask), object list rendering (no overlays yet).
- **Demo:** a real lecture slide is captured, sent to Claude, and its extracted text/equations/objects appear in the sidebar within the <8s fresh-analysis target.
- **Traces to:** "Extract text," "Extract equations," "Analyze diagrams with a vision model."

## Milestone 3 — Interactive Objects & Slide Chat (Weeks 5–7)

**Goal:** bounding-box interaction and slide-grounded Q&A.

- Overlay renderer (`ObjectOverlay`/`HoverOutline`/`SelectionBox`/`FloatingToolbar`) with hover/click/double-click/right-click behavior per the Premium UI Guide.
- `ChatService` (Figure and Slide query modes only at this stage), `POST /chat` SSE streaming end-to-end.
- Object Actions from the playbook: Explain, Summarize, Copy LaTeX, Copy Markdown (Generate Quiz/Flashcards/Open References land in later milestones).
- **Demo:** click a diagram on a live slide, ask "explain this," get a streamed, grounded answer with the diagram highlighted.
- **Traces to:** "Answer questions grounded in the current slide," "Highlight the referenced region," "Bounding-box object interaction" (PRD Core MVP).

## Milestone 4 — Presentation-Wide Retrieval (Weeks 7–9)

**Goal:** RAG across an entire indexed deck.

- `EmbeddingService` (Voyage AI default, local fallback) + `embeddings` table + HNSW indexing (see [DATA_MODEL.md](./DATA_MODEL.md) §3–4).
- `RetrievalService` (top-k object/slide retrieval scoped to a presentation).
- `ChatService` Presentation query mode; Auto mode heuristic (see [ARCHITECTURE.md](./ARCHITECTURE.md) §4.3).
- Batch indexing path (Message Batches API) for "index this whole deck now" vs. incremental live-capture indexing.
- **Demo:** ask a question referencing an earlier slide in the same deck; the answer cites and links back to the correct slide.
- **Traces to:** "Support presentation-wide search," PRD's Presentation query mode.

## Milestone 5 — Quiz, Notes, Concepts & Release Candidate (Weeks 9–12)

**Goal:** remaining product surface, then hardening.

- Weeks 9–10: `QuizService` + `NotesService` (`quiz.v1`/`notes.v1` prompts), basic concept-graph view (per-presentation list of extracted concepts with links to source objects — "Concept graph (basic)" per the PRD, not the full future-vision knowledge graph).
- Week 9: UI Polish — dark mode, keyboard shortcuts, empty/loading/error states everywhere (per the Premium UI Guide's pre-release checklist).
- Week 10: Optimization — cache hit-rate tuning, prompt-cache breakpoint audit (see [PROMPTS.md](./PROMPTS.md) §6), capture-latency profiling against the <150ms target.
- Week 11: Documentation — README, deployment guide, developer guide, this docs suite brought current with whatever changed during implementation.
- Week 12: Release Candidate — full regression pass against the Definition of Done (below), demo recording.
- **Demo:** a full session — capture, analyze, ask, quiz, notes — on a real lecture deck, meeting all Definition of Done criteria.
- **Traces to:** "Generate Quiz," "Generate Flashcards" (stretch — may slip to a fast-follow if Week 9–10 is tight), "Concept graph (basic)."

## Definition of Done (per Engineering Playbook, applied every milestone)

A milestone's slice is done only if: code builds; tests pass (unit per service, API per router, integration for the capture→analyze→retrieve path); the relevant API is documented (this contract, kept current); the UI works end-to-end for that slice; logs are present; errors are handled without crashing the sidebar; the slice has been reviewed; a demo has been recorded.

## Explicit Out of Scope (v1) — per MVP Build Spec

Multi-agent orchestration; editable diagram generation; automatic code generation from every diagram; cross-course memory; advanced theorem proving. These remain listed in the ["Future Versions"](../VisionLearn_PRD.md) section of the PRD and are not scheduled in this roadmap.

## Traceability Table

| MVP Success Criterion (Build Spec) | Milestone |
|---|---|
| Detect current slide | M1 |
| Capture visible slide | M1 |
| Extract text | M2 |
| Extract equations | M2 |
| Analyze diagrams with a vision model | M2 |
| Answer questions grounded in the current slide | M3 |
| Support presentation-wide search | M4 |
| Highlight the referenced region | M3 |
