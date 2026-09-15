# Dev Tools

Developer utilities — not part of the shipped product. The actual product
UI is the Chrome extension's side panel (`extension/`).

## `test-harness.html`

A small, self-contained page for testing the backend directly without
fighting Swagger UI's multipart-form quirks (empty vs. placeholder string
fields for optional parameters — the source of the `422 Malformed
presentation_id` errors you'd hit at `/docs`).

**Usage:** just open the file directly in a browser (double-click it, or
`file://` URL) — no server needed. It talks to `http://localhost:8001` by
default (matching `docker-compose.yml`); change the Backend URL field if
yours differs.

Settings (backend URL, API key) are saved to the browser's `localStorage`
only, never sent anywhere except the backend URL you configure.

Works because the backend's CORS is intentionally wide open for a
local-first, single-user deployment (see
[docs/adr/ADR-007-local-first-deployment.md](../docs/adr/ADR-007-local-first-deployment.md)) —
the real access control is the `X-API-Key` header, which this page sends
for you.

## `eval_algorithms.py`

A manual eval harness for the "algorithm" chat mode
([docs/AlgorithmsMVP.md](../docs/AlgorithmsMVP.md)) — hits the real chat
model over HTTP against a small hand-picked set of cases spanning all 5
shipped phases (loop complexity, recurrences, sorting/search traces,
BFS/DFS/Dijkstra, and each explanation mode). Costs real API money and
isn't fully deterministic (the LLM can phrase things differently call to
call, especially on the softer heuristic checks), so it's run by hand,
not part of `pytest`/CI.

**Usage** (with the Docker stack up — `docker compose up -d db redis
backend`):

```bash
cd backend && LOCAL_API_KEY=<your .env value> python ../tools/eval_algorithms.py
```

Seeds slide/object rows directly via the repositories (bypassing
`/slides/analyze` and the VLM) so failures point at the chat prompt, not
at VLM extraction quality — that's a separate, already-observed source
of variance (see `AlgorithmsMVP.md` Phase 4's missing-edge-weight note).
