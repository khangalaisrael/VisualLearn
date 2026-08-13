# VisionLearn AI — Backend

FastAPI backend. `GET /health`, `POST /slides/analyze` wired end-to-end,
with real vision analysis when a provider key is set — `OpenAIVLMAnalyzer`
(default, if `OPENAI_API_KEY` is set) or `ClaudeVLMAnalyzer` (if only
`ANTHROPIC_API_KEY` is set) — and a hardcoded placeholder analyzer if
neither is configured. See [docs/ROADMAP.md](../docs/ROADMAP.md) Milestone 2
and [docs/adr/ADR-009-openai-as-active-vlm-provider.md](../docs/adr/ADR-009-openai-as-active-vlm-provider.md)
(amends [ADR-004](../docs/adr/ADR-004-vlm-first-pipeline.md)).

`POST /chat` (Milestone 3) streams SSE responses for Figure/Slide-mode
questions grounded in a slide's extracted objects, via the same
OpenAI-first provider selection (`OpenAIChatService`/`ClaudeChatService`
— see ADR-009's Milestone 3 addendum); returns `503` if neither provider
key is set (chat has no placeholder — a canned answer would mislead a
real question).

## Running the full stack (recommended)

From the repo root:

```bash
cp .env.example .env   # then set LOCAL_API_KEY and OPENAI_API_KEY (or ANTHROPIC_API_KEY)
docker compose up --build
```

This starts PostgreSQL (with pgvector), Redis, and the backend on
`http://localhost:8001` (host port 8001, not 8000 — see
docker-compose.yml's `backend.ports` comment: some environments have
another local process already bound to 127.0.0.1:8000). Apply migrations
once the `db` service is healthy:

```bash
docker compose exec backend alembic upgrade head
```

Without either provider key set, the backend still runs — `/slides/analyze`
falls back to a placeholder analyzer (see
`app/services/slide_analyzer.py:PlaceholderSlideAnalyzer`) and
`GET /health` reports `model_provider: false`.

Check it's alive:

```bash
curl http://localhost:8001/api/v1/health
```

Interactive API docs (Swagger UI): `http://localhost:8001/docs`.

## Always-on local setup

VisionLearn is local-first by design ([ADR-007](../docs/adr/ADR-007-local-first-deployment.md)) — the
backend only runs while `docker compose up` is active on your machine. To have it
survive reboots and container crashes without manually running that command each time:

1. **Enable Docker Desktop auto-start**: Docker Desktop → Settings → General →
   "Start Docker Desktop when you sign in." All three services already use
   `restart: unless-stopped` in `docker-compose.yml`, so once the Docker daemon is
   back, they resume on their own — as long as they weren't explicitly stopped with
   `docker compose down`.
2. **Register a login task to bring the stack up**, covering first-run and the
   `docker compose down` case: use `scripts/start-backend.ps1` (a thin wrapper
   around `docker compose up -d` from the repo root) as a Windows Task Scheduler
   entry triggered "At log on":
   ```powershell
   $action = New-ScheduledTaskAction -Execute "powershell.exe" `
     -Argument "-NoProfile -ExecutionPolicy Bypass -File `"C:\Users\israe\Desktop\VisualLearn\scripts\start-backend.ps1`""
   $trigger = New-ScheduledTaskTrigger -AtLogOn
   Register-ScheduledTask -TaskName "VisionLearnBackend" -Action $action -Trigger $trigger
   ```
3. **Verify it came back up** after a reboot:
   ```bash
   curl http://localhost:8001/api/v1/health
   ```
   or open the extension's Settings tab and click "Test Connection."

## Local development (outside Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

Copy `.env.example` (repo root) to `.env` and set `LOCAL_API_KEY` (and
`OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` for real analysis). Point
`DATABASE_URL`/`REDIS_URL` at a running Postgres/Redis (e.g.
`docker compose up db redis -d` from the root, which exposes both on
localhost), then:

```bash
uvicorn app.main:app --reload
alembic upgrade head
```

Prompts are loaded from the top-level `../prompts/` directory
(`app/core/prompt_loader.py`) — no extra setup needed when running from a
checkout, since the loader resolves it relative to its own file location.

## Tests

From the repo root (uses SQLite in-memory and a fake Redis — no Docker, no
migrations, and no real API calls to either provider required or made):

```bash
pip install -e "backend[dev]"
pytest
```

## Layout

```
app/
  api/          # FastAPI routers (thin — no business logic)
  services/     # SlideAnalyzer protocol + PlaceholderSlideAnalyzer /
                #   OpenAIVLMAnalyzer / ClaudeVLMAnalyzer (shared schema in
                #   vlm_output.py), graph_topology.py (hybrid graph
                #   structure extraction, see ADR-010), CacheService,
                #   HealthService
  repositories/ # DB access per aggregate
  models/       # Pydantic schemas (API) + SQLAlchemy ORM models (DB)
  db/           # engine/session, cross-dialect GUID type
  core/         # settings, logging, redis client, prompt loader
alembic/        # migrations — see docs/DATA_MODEL.md for the target schema
                #   0001: users, presentations, slides (Milestone 1)
                #   0002: cache_entries (Milestone 2)
```
