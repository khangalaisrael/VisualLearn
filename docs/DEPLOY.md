# Deploying VisionLearn publicly

> **Free, no-card option:** [DEPLOY_RENDER.md](DEPLOY_RENDER.md) (Render + Neon + Upstash) is the currently recommended path. This page covers a self-managed VM (Oracle Cloud), which needs a Pay As You Go card verification in practice.

Runbook for [PublicHostingMVP.md](PublicHostingMVP.md) **Phase 1**: the existing backend on an Oracle Cloud Always Free VM behind HTTPS, plus building the extension against that URL.

> **Not safe to share yet.** Until Phase 2 (OAuth) and Phase 4 (rate limits) land, the only access control is the shared `LOCAL_API_KEY`. Anyone holding it can spend your OpenAI/Anthropic credit. Treat the deployment as private staging, and set spending caps in the provider dashboards.

## What's in the repo

| File | Purpose |
|---|---|
| `docker-compose.prod.yml` | Production stack: db + redis (no public ports), backend (baked image, 2 workers, no `--reload`), Caddy on 80/443 |
| `deploy/Caddyfile` | Automatic Let's Encrypt HTTPS for `$DOMAIN`, reverse-proxies to the backend, SSE-friendly flushing for `/chat` |
| `scripts/setup-oracle-vm.sh` | Installs Docker, opens 80/443 in the VM's own iptables |
| `extension/` `VITE_BACKEND_URL` | Build-time default backend URL for a hosted extension build |

## 1. Create the VM (you, in the Oracle console)

1. Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/). A card is needed for verification. Always Free resources aren't charged.
2. **Compute → Instances → Create instance**
   - Image: **Canonical Ubuntu 24.04**
   - Shape: **Ampere → VM.Standard.A1.Flex**, 2 OCPU / 12 GB
   - Download the generated SSH private key (or paste your public key)
   - If you get "Out of capacity", try another availability domain or retry later. Free A1 capacity is scarce in popular regions.
3. **Networking → Virtual Cloud Networks → your VCN → Security Lists → Default** → *Add Ingress Rules*:
   - Source `0.0.0.0/0`, TCP, destination port `80`
   - Source `0.0.0.0/0`, TCP, destination port `443`
4. Note the instance's **public IP**.

## 2. Pick a hostname

- **Own a domain:** add an `A` record, e.g. `api.yourdomain.com → <public IP>`.
- **No domain:** use `<ip-with-dashes>.sslip.io`, e.g. IP `129.146.1.2` → `129-146-1-2.sslip.io`. It resolves to that IP automatically and Let's Encrypt accepts it.

## 3. Bring up the stack (on the VM)

```bash
ssh -i <key> ubuntu@<public IP>
git clone https://github.com/khangalaisrael/VisualLearn.git
cd VisualLearn
bash scripts/setup-oracle-vm.sh
exit   # log back in so the docker group applies
```

```bash
ssh -i <key> ubuntu@<public IP>
cd VisualLearn
cp .env.example .env
nano .env
```

Set at minimum:

```
ENVIRONMENT=production
POSTGRES_PASSWORD=<openssl rand -hex 24>
LOCAL_API_KEY=<openssl rand -hex 32>
OPENAI_API_KEY=sk-...          # and/or ANTHROPIC_API_KEY
DOMAIN=<your hostname from step 2>
ACME_EMAIL=you@example.com
```

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
curl https://$DOMAIN/api/v1/health     # from your laptop; expect JSON with status ok
```

Updating later:

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Logs: `docker compose -f docker-compose.prod.yml logs -f backend caddy`

### Troubleshooting

- **Health check times out from outside:** one of Oracle's two firewalls is still closed. Check the Security List rule (step 1.3) and run `sudo iptables -L INPUT -n --line-numbers` on the VM. The 80/443 ACCEPT rules must come *before* the `REJECT` line. Re-run `scripts/setup-oracle-vm.sh`.
- **Caddy logs certificate errors:** DNS doesn't point at the VM yet, or port 80 is blocked (Let's Encrypt validates over HTTP).
- **ARM build issues:** all images used (`python:3.12-slim`, `pgvector/pgvector:pg16`, `redis:7-alpine`, `caddy:2-alpine`) publish arm64 variants, so none are expected.

## 4. Build the extension against the hosted backend

```bash
cd extension
npm ci
VITE_BACKEND_URL=https://<your hostname> npm run build
```

Load `extension/dist` via `chrome://extensions` → Developer mode → **Load unpacked**. In the side panel's Settings tab, paste the `LOCAL_API_KEY` from the VM's `.env`, then click Save and Test Connection. The URL field already defaults to the hosted URL. It can still be overridden, so pointing at a local backend keeps working.

## Costs & limits — re-check before going public

- **Oracle: $0** as long as only Always Free-eligible resources exist (one A1.Flex VM ≤ the free OCPU/RAM pool, boot volume within 200 GB total block storage, ≤10 TB/month egress). Oracle bills resources *created*, not users served: more traffic makes the VM slower, not pricier. The backend stores extracted text and chat only, never slide images, so disk use stays tiny.
- **Ways to accidentally pay Oracle:** a non-free shape, a second large VM or extra block volumes, Object Storage beyond the free tier, paid load balancers/managed services. Look for the "Always Free-eligible" label. Oracle revises the free limits occasionally; re-check its Always Free page.
- **Set a $1 budget alert** (Billing → Budgets) so any charge emails you immediately.
- **The real cost is the AI provider:** ~$0.01–0.017 per capture on gpt-4o (~16x less on gpt-4o-mini), plus chat. Set a monthly spending cap in the OpenAI/Anthropic dashboards *before* anyone else has the API key, and don't distribute publicly until Phase 2 (sign-in) and Phase 4 (rate limits) exist.
- **Johannesburg A1 capacity:** "Out of capacity" is common on free-only accounts (one availability domain). Upgrading to Pay As You Go usually resolves it; Always Free resources stay free on PAYG.

## What's next

See [PublicHostingMVP.md](PublicHostingMVP.md): Phase 2 (Google sign-in replaces the shared key), Phase 3 (per-user data isolation), Phase 4 (rate limits), Phase 5 (privacy policy + Chrome Web Store submission). Don't submit to the store before Phases 2–4.
