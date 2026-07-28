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
