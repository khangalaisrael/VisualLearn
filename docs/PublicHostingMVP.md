# Public Hosting — Phased Plan

VisionLearn is currently local-first by deliberate choice ([ADR-007](adr/ADR-007-local-first-deployment.md)): each user runs their own Docker backend, no auth beyond a shared `.env` secret. Making the extension installable by the public means crossing that boundary — a hosted backend, real user accounts, and real ongoing cost. ADR-007 itself flagged this as "roughly 3-4 weeks of infrastructure work"; this doc breaks that into shippable phases, same approach as `AlgorithmsMVP.md`.

**Decisions already made** (2026-09-15, direct request): hosting on **Oracle Cloud's Always Free tier** (a permanent free Ampere A1 ARM VM — 2 OCPU/12GB RAM/200GB storage as of the tier's August 2026 sizing — switched from an initial Fly.io plan specifically to avoid per-second metered billing; see "Why Oracle over Fly.io" below), auth via **Google/GitHub OAuth sign-in**, project owner pays OpenAI/Anthropic usage for genuinely public/unknown scale, with spending caps configured directly in the provider dashboards (OpenAI + Anthropic) rather than a fixed dollar figure here — the app still needs its own enforceable per-user rate limits regardless of the billing cap, since a global cap alone doesn't stop one user (or bot) from exhausting it.

**Why Oracle over Fly.io:** Fly.io bills per-second for compute — real but modest ongoing cost (~$5-15/month at small scale). Oracle's Always Free tier is a genuine permanent $0 allocation, not a trial credit, and — unlike Fly's "deploy a Docker Machine" model — it's a real VM, so the existing `docker-compose.yml` runs on it essentially unchanged, the same as on a laptop today. Tradeoffs accepted: Oracle's free ARM capacity can be hard to actually provision in popular regions, its console/UX has a rougher reputation than Fly's, and there's more manual ops work (no managed Postgres/Redis add-ons, no built-in TLS — a reverse proxy with Let's Encrypt is needed for HTTPS) since it's a bare VM, not a PaaS.

Ordering principle: get a real public URL serving the existing stack first (proves the deployment pipeline, zero auth risk), then layer in identity, isolation, and abuse prevention — each phase independently shippable, matching how the Algorithms MVP phases worked.

---

## Phase 1 — Deploy the existing stack to an Oracle Cloud Always Free VM, unchanged

**Goal:** the exact backend that works today (`docker-compose.yml`'s `db`/`redis`/`backend` services), reachable at a public HTTPS URL instead of `localhost:8001`. No auth changes, no code changes to the app itself — this phase is purely deployment plumbing, so it's the lowest-risk place to start and immediately validates the whole pipeline (a real VM → Docker Compose → real API calls) before any harder work.

**Requires from you** (things I can't do on your behalf — account/payment-method creation isn't something I should be doing with your credentials):
1. An Oracle Cloud account ([oracle.com/cloud/free](https://www.oracle.com/cloud/free/)) — needs a credit card for identity verification even though the Always Free tier itself won't charge it.
2. Provision an **Ampere A1 (ARM) Always Free compute instance** — Ubuntu is the simplest image choice (Docker installs cleanly there). Pick a shape within the free 2 OCPU/12GB pool (one 2-OCPU/12GB instance, or split it — one instance is simplest for this).
3. During creation, download the SSH key pair Oracle generates (or supply your own public key) — this is how both of us reach the VM afterward.
4. In the VM's **Virtual Cloud Network → Security List**, open inbound ports 80 and 443 (HTTP/HTTPS) in addition to the default 22 (SSH) — Oracle blocks all inbound traffic by default beyond SSH, unlike most other clouds.
5. Note the VM's public IP (and set up a domain pointing at it, if you have one — needed for a real TLS certificate; without one we can still get HTTPS via a service like nip.io or a Let's Encrypt DNS-01 challenge, slightly more setup).

**Once you have SSH access to the VM**, hand me the IP (and confirm the security list is open) and I'll take it from there: install Docker + Compose, clone the repo, set up `.env` with production secrets (never committed), add a reverse proxy (Caddy — simplest automatic-HTTPS option) in front of the existing `docker-compose.yml`, and bring the stack up.

**What changes in the repo:**
- A `Caddyfile` or small proxy config (new) — TLS termination + routing to the existing `backend` service, since Oracle's VM has no built-in load balancer/TLS the way Fly.io would.
- Secrets stay exactly as they are today (`.env`, gitignored) — just populated with production values on the VM instead of your laptop.
- `extension/src/shared/api-client.ts` / Settings tab: backend URL becomes the VM's public URL by default instead of `localhost:8001` (still overridable, so local dev is unaffected).

**Explicitly not in this phase:** no auth changes — still the single shared `LOCAL_API_KEY` model. This means the deployed backend is *reachable* by the public but not yet *safe* to actually hand out to the public (anyone with the URL and the key can rack up API costs) — that's Phase 2/4. Treat this phase's URL as a private staging environment, not something to share yet.

## Phase 2 — Google/GitHub OAuth sign-in

**Goal:** real per-user identity. A user installs the extension, signs in with Google or GitHub, and the extension holds a backend-issued token instead of a shared static key.

**Approach:** Chrome extensions have a first-class flow for Google sign-in (`chrome.identity.getAuthToken`) — start there since it needs no redirect-page hosting. GitHub (and Google as a fallback) can use `chrome.identity.launchWebAuthFlow`, which needs a small OAuth callback page. Backend: a new `/auth/*` flow that verifies the provider token, creates/looks up a `User` row (the schema already reserves `user_id` columns per ADR-007 — this phase is what finally populates them), and issues its own session token the extension stores and sends as `Authorization: Bearer <token>` (also already reserved in `API_CONTRACT.md`).

**In scope:** Google sign-in first (simpler extension-side flow), `User` table + migration, session token issuance/verification middleware, Settings tab UI for sign-in/sign-out.
**Deferred to this phase's own follow-up:** GitHub sign-in (same backend shape, different extension-side flow — add once Google is proven).

## Phase 3 — Multi-tenant data isolation

**Goal:** one user's slides, captures, and conversations are invisible to every other user.

Every relevant router/repository call gets scoped by the authenticated `user_id` from Phase 2's token — presentations, slides, objects, conversations, messages. This is mostly plumbing (the columns already exist), but it's a correctness-critical phase: a bug here is a real privacy incident, not a cosmetic one, so it needs deliberate test coverage (a test asserting user A's `GET`/chat calls 404 or reject on user B's `presentation_id`/`slide_id`, not just "works for the happy path").

## Phase 4 — Rate limiting & abuse prevention

**Goal:** no single user (or bot hitting the API directly, bypassing the extension) can run up unbounded cost even within an overall Fly.io/OpenAI/Anthropic billing cap.

Redis-backed per-user sliding-window limits (Redis is already in the stack) on both `/slides/analyze` (the expensive VLM call) and `/chat` — e.g. N captures and M chat messages per user per day, returning a clear "rate limited, try again in X" response the extension surfaces instead of a raw error. Exact numbers should be tuned against real OpenAI/Anthropic pricing once Phase 1's Fly.io costs are visible, not guessed here.

## Phase 5 — Privacy policy & Chrome Web Store listing

**Goal:** legally and practically ready to submit to the Chrome Web Store.

- A real privacy policy: captured slide images are sent to a third-party AI provider (OpenAI/Anthropic) for analysis, what's stored (conversations, captured slides) and for how long, how a user deletes their data. This is a real document, not boilerplate — lecture slides can contain copyrighted course material, which is worth being explicit about in the policy (VisionLearn analyzes, doesn't redistribute, but users should know their content leaves their machine).
- Store listing assets: icon set, screenshots, description.
- $5 one-time Chrome Web Store developer registration fee, package `extension/dist` as a `.zip`, submit for review (review turnaround is typically a few days, can be longer).

---

## What this file is not

Not a commitment to build all 5 phases in one sitting — Phase 1 alone (a working public URL) is a meaningful, demoable checkpoint. Phases 2-5 involve real external account setup (Fly.io billing, Google/GitHub OAuth app registration) that only you can do, so each phase's start is a natural pause point to confirm before continuing.
