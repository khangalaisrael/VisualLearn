# ADR-001: Use FastAPI for the Backend

## Status
Accepted

## Context
The backend needs typed request/response validation, async support (for concurrent Claude API calls and SSE streaming), and low ceremony for a small team building over ~12 weeks. The PRD's Non-functional Requirements explicitly call for "Typed APIs."

## Decision
Use FastAPI (Python 3.12) as the backend framework.

## Rationale
- **Typed by default.** Pydantic models double as request/response validation and as the OpenAPI-documented contract ([API_CONTRACT.md](../API_CONTRACT.md)), satisfying the PRD's typing requirement without extra tooling.
- **Native async + streaming.** `POST /chat` needs to relay a Claude streaming response as SSE; FastAPI's async support and `StreamingResponse` make this straightforward.
- **Ecosystem fit.** The Anthropic Python SDK, `pgvector`'s Python bindings, and Voyage AI's client are all first-class in the Python ecosystem the team is already targeting per the specs (`Python 3.12`, `FastAPI` explicitly named in the MVP Build Spec's tech stack).
- **Low ceremony for a solo/small-team build.** Compared to Django, FastAPI adds less boilerplate for a service-oriented, API-only backend with no server-rendered views.

## Alternatives Considered
- **Flask** — mature but requires bolting on async support and typed validation separately; more manual work to match the "typed APIs" requirement.
- **Django + DRF** — heavier than needed for an API-only backend with no admin/CMS use case; async support historically weaker than FastAPI's.
- **Node/Express (TypeScript)** — would let backend and extension share a language, but the specs already commit to a Python AI/backend stack and Python has stronger data-science/embedding library support for future specialized-pipeline work ([ADR-004](./ADR-004-vlm-first-pipeline.md)).

## Consequences
- The team needs Python + TypeScript proficiency (extension is TS regardless — see [ADR-008](./ADR-008-chrome-side-panel.md)), not just one language end-to-end.
- Async discipline is required throughout the service layer to avoid blocking the event loop during Claude API calls.
