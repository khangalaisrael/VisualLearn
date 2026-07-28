# VisionLearn AI — Chrome Extension

Manifest, content-script placeholder (reserved for the future overlay
renderer — capture is manual-only, see below), service worker
(capture + API client), and side panel registration (see
[docs/ROADMAP.md](../docs/ROADMAP.md)). The side panel currently has
Ask (functional — capture, VLM analysis, and Slide-mode chat via
`POST /chat`) and Settings (backend URL/API key config) tabs; Concepts,
Notes, and Quiz remain shells pending Milestone 5. History and the
bounding-box overlay renderer aren't built yet.

## Setup

```bash
npm install
npm run dev      # dev server with HMR
npm run build    # production build to dist/
```

## Load the unpacked extension

1. `npm run build` (or `npm run dev` for HMR during development)
2. Open `chrome://extensions`, enable Developer Mode
3. "Load unpacked" → select `extension/dist`

## Backend connection

The extension talks to the local backend at `http://127.0.0.1:8001` by
default (port 8001, not 8000 — see docker-compose.yml's `backend.ports`
comment) and must send the same `LOCAL_API_KEY` configured in the
backend's `.env` (see
[docs/adr/ADR-007-local-first-deployment.md](../docs/adr/ADR-007-local-first-deployment.md)).

Configure this from the **Settings** tab in the side panel: paste the
backend URL and your `LOCAL_API_KEY`, click Save, then Test Connection to
confirm the backend is reachable and a model provider (`OPENAI_API_KEY`
or `ANTHROPIC_API_KEY`) is configured. Values are stored in
`chrome.storage.local` (`src/shared/api-client.ts` `getConfig`/`setConfig`)
— no rebuild needed to change them.

## Testing against local slide files

Chrome extensions don't get `file://` access by default even with broad
host permissions — it's a separate per-extension toggle. If your slides
are local PDFs (export PPTX to PDF first; Chrome doesn't render PPTX
natively): `chrome://extensions` → VisionLearn AI card → Details → enable
"Allow access to file URLs". Then open the PDF via a `file:///...` URL
and capture as normal.

## Demo

1. Start the backend (`docker compose up --build` from the repo root, then
   `docker compose exec backend alembic upgrade head`; see
   [backend/README.md](../backend/README.md)).
2. Load the extension as above, then configure Settings as above.
3. Open a slide (a PDF, a live Google Slides deck, any page with
   text/diagrams), click the VisionLearn AI toolbar icon to open the side
   panel.
4. Click "Capture Current Slide" — extracted objects (title, paragraphs,
   equations, diagrams) appear within a few seconds.
5. In the "Ask about this slide" box, type a question and hit Send — a
   grounded answer streams in via `POST /chat` (Milestone 3, Slide query
   mode). Figure mode (asking about one selected object) isn't wired up
   yet — it needs the overlay renderer, which doesn't exist yet.
