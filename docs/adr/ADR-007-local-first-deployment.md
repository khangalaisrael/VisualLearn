# ADR-007: Local-First Deployment with a Multi-Tenant-Ready Schema (User Decision)

## Status
Accepted — confirmed directly by the project owner during architecture planning.

## Context
The project owner was asked what the deployment target should be for the first few months: a local single-user Docker Compose stack, or a hosted multi-user platform with accounts, OAuth, and per-user rate limiting from day one. They chose local-first.

## Decision
Target a single-user, local Docker Compose deployment (FastAPI + PostgreSQL/pgvector + Redis) for the MVP and the first several months, with no authentication beyond an API key in `.env`. The data model, however, is designed multi-tenant-ready from the start: every table that will eventually need per-user scoping already has a nullable `user_id` column ([DATA_MODEL.md](../DATA_MODEL.md) §1), and the API contract reserves an (unused) `Authorization` header slot and rate-limit response headers on every endpoint ([API_CONTRACT.md](../API_CONTRACT.md) §1).

## Rationale
- **Matches the actual near-term goal.** The specs describe a solo/small-team 12-week build ([ROADMAP.md](../ROADMAP.md)); building multi-user auth, per-tenant isolation, and hosting infrastructure now would spend weeks of the schedule on capability nobody needs yet, directly working against the Playbook's "Prefer simple architecture over clever architecture."
- **Avoids the worse alternative: retrofitting multi-tenancy later.** Rather than deferring multi-tenancy concerns entirely (which would mean schema migrations and backfills later), the schema and contract reserve the necessary seams now, at near-zero cost, so hosted mode becomes an additive change (auth middleware, populate `user_id`, enforce rate limits) rather than a breaking one.
- **Lower security surface for the MVP.** No credential storage, no session management, no OAuth flow to secure — the local API key model matches the actual threat model of a tool running on the user's own machine.

## Alternatives Considered
- **Hosted multi-user platform from day one.** Would let the product be shared/tested by others sooner, but adds roughly 3–4 weeks of infrastructure work (accounts, OAuth, per-user rate limits, encrypted conversation storage, cloud hosting) before any core AI feature ships — directly conflicts with the "vertical slices, always demoable" principle for the *AI features* that are the actual product differentiator.
- **Local-first with no forward-looking schema design** (add `user_id` etc. only when hosting is actually built). Saves a small amount of upfront design time but creates real migration/backfill risk later, and the reserved columns cost essentially nothing to include now.

## Consequences
- Rate limiting, encrypted conversation storage (per the Playbook's Security section), and auth middleware are explicitly deferred, not designed in detail here — they become a dedicated future milestone, not part of this roadmap's 12 weeks.
- The single local user is either an implicit `NULL` `user_id` or a seeded row; whichever is chosen must be applied consistently across the first migration (implementation detail, not an architectural one).
- Anthropic API keys and the Voyage AI key ([ADR-006](./ADR-006-embedding-provider.md)) live in the backend's `.env` only — the extension never holds a credential, which remains true even after a future move to hosted mode.
