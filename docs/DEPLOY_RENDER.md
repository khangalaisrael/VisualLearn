# Deploying on Render + Neon (free, no card)

The $0 hosting path: the backend runs as a **Render free web service**, Postgres is **Neon**, and Redis is **Upstash** (optional). As of 2026, none of these asked for a payment card on their free tiers; re-check at sign-up. For a self-managed VM instead, see [DEPLOY.md](DEPLOY.md).

> **Not safe to share publicly yet.** Until sign-in (Phase 2) and per-user rate limits (Phase 4) from [PublicHostingMVP.md](PublicHostingMVP.md) exist, the only access control is the shared `LOCAL_API_KEY`. Anyone holding it can spend your Anthropic credit. Set a monthly spend limit in the Anthropic console and keep auto-reload off.

## How it fits together

| Piece | Where | Notes |
|---|---|---|
| Backend (FastAPI) | Render free web service | `https://<name>.onrender.com`, HTTPS built in. Built from `deploy/hosted/Dockerfile` per `render.yaml`; migrations run on every start. Redeploys on every push to `main`. |
| Database | Neon Postgres | Paste Neon's connection string unchanged; `app/db/url.py` converts it for asyncpg (SSL included). Don't use Render's free Postgres: it expires after about 30 days. |
| Cache | Upstash Redis (optional) | Without `REDIS_URL` the analysis cache runs on Postgres alone and `/health` reports `"cache": true` as long as the database is up. Not needed at small scale. |
| Keep-awake | cron-job.org (optional) | Pings `/api/v1/health` every 10 minutes so the service doesn't sleep. |

**Free-tier limits (2026; check Render's pricing page):**
- 512 MB RAM and 0.1 CPU. The app runs one async worker; it's mostly waiting on Claude, so it copes with a class capturing at once, just more slowly than a paid instance.
- Sleeps after 15 minutes without requests; the next request takes about 30–60 s to wake it.
- 750 instance-hours a month per workspace. One service running all month uses at most 744.
- 5 GB bandwidth a month. Captures are downscaled to JPEG in the extension (about 0.2–0.4 MB), and answers are a few KB.

## 1. Neon (database)

1. Sign up at [neon.tech](https://neon.tech) and create a project. US East is closest to Render's default Oregon/Virginia regions; match regions if you can.
2. Click **Connect**, **turn off "Connection pooling"** (the host must not contain `-pooler`; PgBouncer breaks asyncpg's prepared statements), and copy the connection string. Use it exactly as shown, `?sslmode=require...` included.

## 2. Upstash (Redis, optional)

Create a free Redis database at [upstash.com](https://upstash.com) and copy its **`rediss://...`** URL (TLS, note the double `s`).

## 3. Render (backend)

1. Sign up at [render.com](https://render.com) **with GitHub**, and allow it access to this repository.
2. **New → Blueprint**, pick this repository. Render reads `render.yaml` and proposes a free web service called `visionlearn-api`.
3. Fill in the values it asks for:
   - `DATABASE_URL`: the Neon connection string from step 1
   - `ANTHROPIC_API_KEY`: your Claude key (`sk-ant-...`)

   `LOCAL_API_KEY` is generated for you, and `ENVIRONMENT` is preset.
4. **Apply**. The first build takes a few minutes; watch **Logs**. It's live when `https://<name>.onrender.com/api/v1/health` returns JSON with `"db": true`.
5. Optional: add `REDIS_URL` (Upstash) under the service's **Environment** tab; Render redeploys automatically.
6. Copy the generated `LOCAL_API_KEY` from the **Environment** tab. The extension needs it.

Don't set `OPENAI_API_KEY` unless you want OpenAI. If it's set, it takes priority over Anthropic.

Render deploys from `main` (`branch:` in `render.yaml`), so this setup must be merged to `main` first. After that, every push to `main` redeploys.

## 4. Keep it awake (optional)

At [cron-job.org](https://cron-job.org) (free, no card), create a job that requests `https://<name>.onrender.com/api/v1/health` **every 10 minutes**. One always-awake service stays within the 750 free hours. Without this, the first capture after 15 idle minutes waits about a minute; the extension shows "Waking up the server…" and retries automatically (`fetchWakingBackend` in `extension/src/shared/api-client.ts`).

## 4a. Daily cleanup (required for retention)

Chats and the slide content behind them are deleted `CHAT_RETENTION_DAYS` (default 30) after their last message. Render's free plan has no scheduled jobs, so a second cron-job.org job triggers it:

- URL: `https://<name>.onrender.com/api/v1/maintenance/cleanup`
- Method: **POST**, once a day
- Header: `X-API-Key: <LOCAL_API_KEY>`

Expired chats are already hidden on read, so a missed run only delays deletion. The response lists how many rows were removed.

## 5. Point the extension at it

```bash
cd extension
npm ci
VITE_BACKEND_URL=https://<name>.onrender.com npm run build
```

Load `extension/dist` in `chrome://extensions` (Developer mode → **Load unpacked**). In the Settings tab, paste the `LOCAL_API_KEY`, click Save, then Test Connection. Leave both model pickers on **Server default** (Claude Haiku 5.5).

## Troubleshooting

- **Deploy fails / service restarts in a loop**: check **Logs**. `alembic upgrade head` failing usually means `DATABASE_URL` is missing, mistyped, or is the pooled (`-pooler`) endpoint.
- **"Out of memory" in Logs**: make sure `WEB_CONCURRENCY` isn't set above 1 on the free plan.
- **`/health` says `"cache": false`**: `REDIS_URL` is set but Redis is unreachable. Remove the variable or fix the URL.
- **Extension says a model "requires an OpenAI-configured backend"**: set both Settings pickers to **Server default**.
- **Slow when the whole class captures at once**: expected on 0.1 CPU. Render's cheapest paid instance (0.5 CPU) is the fix if it's a problem; set `WEB_CONCURRENCY=2` there.

## Costs

- Render free, Neon free, Upstash free, cron-job.org: **$0**, no card. Free-tier terms change; check each dashboard occasionally.
- Anthropic: about $0.001 per slide capture on Claude Haiku 5.5 (an estimate; downscaled captures use fewer image tokens; the console shows real per-request cost).
