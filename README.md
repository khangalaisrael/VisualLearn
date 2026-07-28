# VisionLearn AI

A Chrome extension and backend platform that understands STEM lecture slides — text, equations, diagrams, charts, and figures — and lets students query them interactively, grounded in the current slide or an entire indexed presentation.

This repository currently holds product specs and architecture documentation. No implementation exists yet — see the roadmap for the build schedule.

## Source Specs

- [VisionLearn_PRD.md](./VisionLearn_PRD.md) — product requirements: vision, users, core MVP scope, sprint plan.
- [VisionLearn_MVP_Build_Spec.md](./VisionLearn_MVP_Build_Spec.md) — MVP success criteria, tech stack, milestone roadmap, out-of-scope list.
- [VisionLearn_Engineering_Playbook.md](./VisionLearn_Engineering_Playbook.md) — engineering methodology, git workflow, Definition of Done, security/observability practices.
- [VisionLearn_Premium_UI_Guide.md](./VisionLearn_Premium_UI_Guide.md) — UI/UX system: layout, design tokens, interaction model, accessibility.

## Architecture Documentation

Produced from the specs above plus two explicit project-owner decisions (VLM-first AI pipeline; local-first deployment) — start with `ARCHITECTURE.md`:

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System design: extension + backend architecture, AI integration (Claude vision/chat, structured outputs, caching), non-functionals. |
| [docs/DATA_MODEL.md](./docs/DATA_MODEL.md) | PostgreSQL + pgvector schema, ER diagram, indexing plan. |
| [docs/API_CONTRACT.md](./docs/API_CONTRACT.md) | REST + SSE contract for every backend endpoint. |
| [docs/PROMPTS.md](./docs/PROMPTS.md) | Prompt library skeleton and versioning/caching conventions. |
| [docs/ROADMAP.md](./docs/ROADMAP.md) | 12-week milestone plan, Definition of Done, traceability to MVP success criteria. |
| [docs/adr/](./docs/adr/) | Architecture Decision Records — why each major technical choice was made. |

### Key decisions at a glance

- **AI pipeline is VLM-first**: one vision call with structured outputs replaces the originally-scoped separate OCR / math-OCR / layout-detection / vision stages, kept swappable behind a `SlideAnalyzer` interface ([ADR-004](./docs/adr/ADR-004-vlm-first-pipeline.md)). OpenAI is the active provider by default, Claude remains fully supported ([ADR-009](./docs/adr/ADR-009-openai-as-active-vlm-provider.md)).
- **Deployment is local-first**: single-user Docker Compose (FastAPI + Postgres/pgvector + Redis), no auth, but a multi-tenant-ready schema so hosting is additive later ([ADR-007](./docs/adr/ADR-007-local-first-deployment.md)).

## Proposed Repository Structure

The PRD and MVP Build Spec each sketch a slightly different folder layout. This structure reconciles them into one, chosen for the [ADR-005](./docs/adr/ADR-005-modular-monolith.md) modular-monolith decision — AI capabilities live as services inside `backend/`, not as a separate top-level `ai/` tree, since they are not independently deployed:

```
visionlearn/
  backend/
    api/          # FastAPI routers
    services/     # SlideAnalyzer, EmbeddingService, RetrievalService, ChatService, QuizService, NotesService, CacheService
    repositories/  # DB access per aggregate
    models/        # Pydantic schemas + ORM models
    db/            # session management, migrations
    core/           # config, logging, cache client, prompt loader
  extension/
    content-script/  # slide-change detection, bounding-box overlay
    service-worker/  # capture, API client, message routing
    sidepanel/       # React + TS + Tailwind UI (Ask/Concepts/Notes/Quiz/History/Settings)
  shared/          # types shared between backend and extension (generated from the API contract) and cross-cutting config
  prompts/         # versioned prompt templates (analysis.v1.md, chat_slide.v1.md, ...) per docs/PROMPTS.md
  docs/            # this documentation suite
  tests/           # unit, service, API, integration
  tools/           # dev-only utilities, not part of the shipped product (e.g. test-harness.html)
```

This is the target layout; every directory shown — including `prompts/`, populated as of Milestone 2 — is scaffolded. `tools/` isn't part of the original proposed structure; it was added as a developer convenience (see [tools/README.md](./tools/README.md)).

## Status

**Milestone 2 (Real Analysis) complete**, plus a graph-structure extraction feature added by direct request. A real `SlideAnalyzer` replaces the Sprint 1 placeholder: `OpenAIVLMAnalyzer` (default, `gpt-4o`) if `OPENAI_API_KEY` is set, `ClaudeVLMAnalyzer` (`claude-opus-4-8`) if only `ANTHROPIC_API_KEY` is set, the placeholder otherwise — see [ADR-009](./docs/adr/ADR-009-openai-as-active-vlm-provider.md). Both share one prompt ([`prompts/analysis.v2.md`](./prompts/analysis.v2.md)) and one output schema (`backend/app/services/vlm_output.py`). A two-layer analysis cache (Redis + `cache_entries`, image-hash keyed, global across presentations — see [docs/API_CONTRACT.md](./docs/API_CONTRACT.md) §2) skips redundant calls and degrades gracefully if Redis is unavailable.

For node/edge graph diagrams (CS algorithm coursework — weighted graphs, trees, networks), a hybrid, two-pass VLM + classical-CV pipeline (`backend/app/services/graph_topology.py`) extracts queryable structure (`SlideObject.graph_structure`: nodes, edges, weights, direction) — vs. ~69-75% edge-attribution accuracy asking the vision model directly, even with majority-voting. Validated against real coursework slides, not just synthetic renders: reliably correct on clean digital slides, best-effort on photos with heavily curved directed edges. See [ADR-010](./docs/adr/ADR-010-hybrid-graph-structure-extraction.md) for the full empirical history, including what real-world testing broke and how it was fixed.

**Milestone 3 backend (slide-grounded chat) is live**: `POST /chat` (`backend/app/api/v1/chat.py`) streams SSE responses for Figure and Slide query modes, backed by `ChatService` (`OpenAIChatService`/`ClaudeChatService`, same OpenAI-first provider selection as analysis — see [ADR-009](./docs/adr/ADR-009-openai-as-active-vlm-provider.md)'s Milestone 3 addendum). Objects, conversations, and messages are now persisted (`objects`/`conversations`/`messages` tables, migration `0003`) so a chat request can resolve `object_id`/`slide_id` to real content. Presentation/General/Auto modes remain M4+ scope (`400` for now).

The extension's Ask tab (`extension/src/sidepanel/tabs/AskTab.tsx`) now calls `/chat` directly in Slide query mode: after a capture, a chat box streams grounded answers over every object detected on that slide, reading the SSE response via `streamChat` (`extension/src/shared/api-client.ts`) since `EventSource` can't carry a POST body. Figure mode (grounded on a single selected object) is not wired up yet — it needs the overlay renderer (`ObjectOverlay`/`HoverOutline`/`SelectionBox`/`FloatingToolbar`), which doesn't exist yet, so there is no way to select a single object to ask about. Concepts/Notes/Quiz remain tab shells.

A **Settings tab** was added ahead of its milestone, by direct request, to replace the devtools-console config workaround: paste the backend URL and `LOCAL_API_KEY`, Save, then Test Connection to confirm reachability and whether a model provider is configured — values persist in `chrome.storage.local`.

Two more direct-request changes: (1) the content script's automatic DOM-mutation slide-change detector (`extension/src/content-script/capture-detector.ts`) was **removed** — it fired on ordinary page DOM churn, not just slide changes, silently burning analysis calls while browsing any page; capture is manual-only now (the "Capture Current Slide" button), and the content script is now a placeholder reserved for the future overlay renderer. (2) Object results and chat answers render properly now: equations typeset as real math via KaTeX (`extension/src/sidepanel/components/MathText.tsx`, recognizing `$$…$$`/`\[…\]`/`$…$`/`\(…\)` delimiters) instead of showing raw LaTeX source, and `table`-type objects render as an actual HTML `<table>` when the extracted text parses as one (`extension/src/sidepanel/components/ObjectCard.tsx`), falling back to a styled preformatted block otherwise.

See [backend/README.md](./backend/README.md) and [extension/README.md](./extension/README.md) for setup, [tools/README.md](./tools/README.md) for the dev test harness, and [docs/ROADMAP.md](./docs/ROADMAP.md) Milestone 3 for what's next.

Milestone 1 (Foundation) — repo scaffold, `GET /health`, the extension shell — is unchanged from before and still complete.
