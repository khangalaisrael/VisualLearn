# Deploying on Hugging Face Spaces + Neon (free, no card)

The $0 hosting path: the backend runs as a **Hugging Face Docker Space**, Postgres is **Neon**, and Redis is **Upstash** (optional). Nothing here needs a payment card. For a self-managed VM instead, see [DEPLOY.md](DEPLOY.md).

> **Not safe to share publicly yet.** Until sign-in (Phase 2) and per-user rate limits (Phase 4) from [PublicHostingMVP.md](PublicHostingMVP.md) exist, the only access control is the shared `LOCAL_API_KEY`. Anyone holding it can spend your Anthropic credit. Set a monthly spend limit in the Anthropic console.

## How it fits together

| Piece | Where | Notes |
|---|---|---|
| Backend (FastAPI) | Hugging Face Docker Space | `https://<user>-<space>.hf.space`, HTTPS built in. Migrations run on every start (`deploy/huggingface/start.sh`). |
| Database | Neon Postgres | Paste Neon's connection string unchanged; `app/db/url.py` converts it for asyncpg (SSL included). |
| Cache | Upstash Redis (optional) | Without it, analysis caching falls back to Postgres and `/health` reports `degraded`, but everything works. |
| Deploys | GitHub Actions | `.github/workflows/deploy-hf-space.yml` pushes `backend/` + `prompts/` to the Space on every push to `main`. |
| Keep-awake | GitHub Actions | `.github/workflows/keep-hf-space-awake.yml` pings `/api/v1/health` every 6 hours. |

## 1. Neon (database)

1. Sign up at [neon.tech](https://neon.tech) with GitHub or Google.
2. Create a project. Pick the region closest to where the Space runs (a US East or EU region works well).
3. On the project dashboard, click **Connect** and copy the connection string.
   - **Turn off "Connection pooling"** first, so the host doesn't contain `-pooler`. The pooled endpoint (PgBouncer) breaks asyncpg's prepared statements.
   - It looks like `postgresql://neondb_owner:xxxx@ep-something-123456.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`. Use it exactly as shown.

## 2. Upstash (Redis, optional)

1. Sign up at [upstash.com](https://upstash.com) and create a **Redis** database (free tier, any nearby region).
2. Copy the **`rediss://...`** connection URL (TLS, note the double `s`).

## 3. Hugging Face Space (backend)

1. Sign up at [huggingface.co](https://huggingface.co).
2. **New → Space**:
   - Name: e.g. `visionlearn`
   - SDK: **Docker** → **Blank** template
   - Hardware: **CPU basic (free)**
   - Visibility: **Public**. A private Space only answers requests that carry a Hugging Face token, which the extension can't safely ship. Your *code* is visible in a public Space; your *secrets* are not.
3. In the Space, open **Settings → Variables and secrets** and add these as **Secrets**:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Neon connection string from step 1 |
   | `LOCAL_API_KEY` | A long random string (e.g. from a password manager). The extension sends this. |
   | `ANTHROPIC_API_KEY` | Your Anthropic key (`sk-ant-...`) |
   | `REDIS_URL` | Upstash `rediss://...` URL (skip if not using Upstash) |
   | `ENVIRONMENT` | `production` |

   Don't set `OPENAI_API_KEY` unless you want OpenAI. If it's set, it takes priority over Anthropic.
4. Create an access token: avatar → **Settings → Access Tokens → Create new token**, type **Write**. Copy it.

## 4. Connect GitHub to the Space

In the GitHub repo: **Settings → Secrets and variables → Actions**:

- **Secrets** tab → `HF_TOKEN` = the write token from step 3.4
- **Variables** tab:
  - `HF_SPACE` = `<your-hf-username>/visionlearn`
  - `HF_SPACE_URL` = `https://<your-hf-username>-visionlearn.hf.space` (shown on the Space page under **⋮ → Embed this Space → Direct URL**)

GitHub only runs workflows that are on the default branch, so these take effect once this work is merged to `main`. The first deploy then runs automatically; later backend changes redeploy on every merge. Any time, **Actions → Deploy backend to Hugging Face → Run workflow** redeploys by hand.

The Space builds for a few minutes (watch **Logs** on the Space page). It's ready when `https://<user>-visionlearn.hf.space/api/v1/health` returns JSON with `"db": true`.

## 5. Point the extension at it

```bash
cd extension
npm ci
VITE_BACKEND_URL=https://<user>-visionlearn.hf.space npm run build
```

Load `extension/dist` in `chrome://extensions` (Developer mode → **Load unpacked**). In the Settings tab, paste the `LOCAL_API_KEY`, click Save, then Test Connection. Leave both model pickers on **Server default** (Claude Haiku 5.5).

## Sleeping

Free Spaces sleep after about 48 hours without traffic, and the first request afterwards takes about a minute while the Space boots.

- The keep-awake workflow pings every 6 hours so it shouldn't get there. GitHub pauses scheduled workflows in repos with no commits for 60 days; re-enable it from the Actions tab if that happens.
- If it does sleep, the extension retries automatically for up to about 2½ minutes and shows "Waking up the server…" so users aren't left staring at a spinner (`fetchWakingBackend` in `extension/src/shared/api-client.ts`).

## Troubleshooting

- **Space shows "Runtime error"**: open **Logs**. `alembic upgrade head` failing usually means `DATABASE_URL` is missing, mistyped, or is the pooled (`-pooler`) endpoint.
- **Deploy workflow fails at "Push to the Space"**: `HF_TOKEN` is missing or read-only, or `HF_SPACE` doesn't match the Space id exactly.
- **`/health` says `"cache": false`**: `REDIS_URL` isn't set or is wrong. Harmless; see the Upstash note above.
- **Extension says a model "requires an OpenAI-configured backend"**: set both Settings pickers to **Server default**.

## Costs & limits

- Hugging Face CPU basic, Neon free and Upstash free: **$0**, no card. Free-tier limits and terms change; check each dashboard occasionally.
- Anthropic: about $0.001 per slide capture on Claude Haiku 5.5 (an estimate; the console shows real per-request cost). Set a monthly spend limit and keep auto-reload off.
