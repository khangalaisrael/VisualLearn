# ADR-002: PostgreSQL + pgvector for Storage and Vector Search

## Status
Accepted

## Context
The system needs both conventional relational storage (presentations, slides, objects, conversations — see [DATA_MODEL.md](../DATA_MODEL.md)) and vector similarity search for presentation-wide retrieval ([ARCHITECTURE.md](../ARCHITECTURE.md) §4.1, `RetrievalService`). The PRD names "PostgreSQL + pgvector" and "Redis cache" directly in its architecture pipeline.

## Decision
Use PostgreSQL with the `pgvector` extension as the single datastore for both relational and vector data, rather than a dedicated vector database.

## Rationale
- **One database, one operational surface.** For a local-first, single-Docker-Compose deployment ([ADR-007](./ADR-007-local-first-deployment.md)), running a second specialized vector store (Pinecone, Weaviate, Qdrant) adds an extra service to operate for no benefit at this scale — the expected corpus size (one user's lecture decks) is well within `pgvector`'s comfortable range with HNSW indexing.
- **Joins for free.** Retrieval needs to combine vector similarity with relational filters (scope to a `presentation_id`, join back to `objects`/`slides` for the actual content) — this is a single SQL query in Postgres, versus a fetch-then-join across two systems with a dedicated vector DB.
- **Matches the spec directly.** Both the PRD and MVP Build Spec name this pairing explicitly.

## Alternatives Considered
- **Dedicated vector DB (Pinecone/Weaviate/Qdrant) + Postgres for relational data.** Better at massive scale (many users, huge corpora) but adds an extra managed service or container, cross-store consistency concerns, and no clear benefit until well past the current scale target. Revisit if/when hosted multi-tenant scale makes single-node Postgres the bottleneck.
- **SQLite + a local vector index (e.g. `sqlite-vss`).** Simpler for a pure single-user local tool, but weaker migration path to hosted multi-user mode ([ADR-007](./ADR-007-local-first-deployment.md)) and less mature `pgvector`-equivalent tooling.

## Consequences
- Vector index maintenance (HNSW rebuilds, dimension changes on embedding-provider swap — see [ADR-006](./ADR-006-embedding-provider.md)) is a Postgres-native concern, documented in [DATA_MODEL.md](../DATA_MODEL.md) §4–5.
- If corpus size ever grows far beyond a single user's decks, a dedicated vector store becomes worth revisiting — explicitly deferred, not designed against now.
