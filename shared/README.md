# Shared Types

Hand-written TypeScript mirrors of the backend's Pydantic schemas
(`backend/app/models/schemas.py`), used by the extension via the `@shared`
alias (see `extension/tsconfig.json` and `extension/vite.config.ts`). See
[docs/API_CONTRACT.md](../docs/API_CONTRACT.md) for the authoritative
contract these types must match.

Kept manually in sync for now. Once the API surface is large enough to
justify it, this should be replaced by codegen from FastAPI's OpenAPI schema
(e.g. `openapi-typescript`) — not built in Sprint 1, to keep scope tight.
