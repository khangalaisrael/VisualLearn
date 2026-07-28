# ADR-005: Modular Monolith with Service Interfaces (Not Microservices)

## Status
Accepted

## Context
The system has several distinct capabilities (slide analysis, embedding, retrieval, chat, quiz, notes, caching) that could be built as independent deployable services. The Engineering Playbook explicitly states: "Keep services independent... Do not split into microservices until necessary." The PRD's Claude Code Rules similarly emphasize "Keep services loosely coupled" without mandating separate deployments.

## Decision
Build a single deployable FastAPI backend (a modular monolith) with each capability implemented as an internal service class defined against a `Protocol` interface ([ARCHITECTURE.md](../ARCHITECTURE.md) §4.1), rather than as separate microservices.

## Rationale
- **No operational justification yet.** Microservices earn their complexity (independent scaling, independent deployment, fault isolation) when a system has traffic patterns or team boundaries that need it. A local-first, single-user MVP ([ADR-007](./ADR-007-local-first-deployment.md)) has neither.
- **Loose coupling without deployment overhead.** Defining each service against a `Protocol` gets the main benefit usually sought from microservices — the ability to swap an implementation (see [ADR-004](./ADR-004-vlm-first-pipeline.md)) without touching callers — without paying for network calls, service discovery, or distributed-transaction concerns between, say, `ChatService` and `RetrievalService`.
- **Directly follows the source specs' explicit instruction**, not just a default preference.

## Alternatives Considered
- **Microservices per capability** (analysis service, retrieval service, chat service as separate deployments). Would allow independent scaling of the expensive analysis path, but at this scale adds Docker Compose complexity, inter-service auth, and network latency for no present benefit. Explicitly named in [ARCHITECTURE.md](../ARCHITECTURE.md) §7 as the most likely future extraction candidate *if* a concrete scaling need arises.
- **Single undifferentiated codebase with no service boundaries.** Faster to write initially but reintroduces the coupling the Playbook warns against — a change to the analysis prompt could accidentally affect chat behavior, and unit testing becomes harder without a protocol boundary to mock.

## Consequences
- Internal discipline is required to keep services genuinely decoupled (depending on protocols, not concrete classes) even though there's no network boundary enforcing it.
- If the analysis pipeline's compute/cost profile ever diverges sharply from the rest of the backend (e.g. needing GPU-backed specialized models per [ADR-004](./ADR-004-vlm-first-pipeline.md)'s future path), extracting it into its own service becomes the natural first split — the protocol boundary already in place makes that extraction mechanical rather than a redesign.
