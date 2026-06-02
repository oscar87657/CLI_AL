# Production deployment

This document describes the live deployment of CLI_AL. **Read this before changing any file listed under [§ Do not touch without coordination](#do-not-touch-without-coordination).**

---

## 1. Live URLs

| Component | URL | Host |
|-----------|-----|------|
| Frontend  | https://cli-al.vercel.app | Vercel (Hobby — free) |
| Backend   | https://cli-al-backend.onrender.com | Render (free plan, Singapore) |
| Database / Auth | Supabase project `cli-al` | Supabase free |
| LLM       | Upstage Solar Pro 3 | Upstage cloud |

Health endpoint: `https://cli-al-backend.onrender.com/health` — should return `{"status":"ok","upstage_configured":true,"supabase_configured":true,"model":"solar-pro3"}`.

---

## 2. Architecture

```
Browser
  │
  ▼
Vercel (Next.js SSR)   ── reads NEXT_PUBLIC_* env at build time
  │  fetch
  ▼
Render (FastAPI)       ── reads UPSTAGE_*, SUPABASE_*, CORS_ALLOW_ORIGINS at runtime
  │
  ├──► Upstage Solar API
  └──► Supabase Postgres
```

Both Vercel and Render auto-deploy on every push to `main`. Pull requests to `main` get a Vercel **Preview URL** automatically; Render does not preview on free plan.

---

## 3. Environment variables

### 3.1 Render (backend)
Set in Render dashboard → service `cli-al-backend` → **Environment**. All marked `sync: false` in `render.yaml`, meaning Render does not store them in git — they must be entered through the dashboard.

| Key | Example | Notes |
|-----|---------|-------|
| `UPSTAGE_API_KEY` | `up_…` | Solar / Document Parse / Embedding |
| `SUPABASE_URL` | `https://xxx.supabase.co` | Project URL |
| `SUPABASE_SECRET_KEY` | `sb_secret_…` | Server-side, bypasses RLS — **never** expose to FE |
| `CORS_ALLOW_ORIGINS` | `https://cli-al.vercel.app` | Comma-separated list of allowed FE origins |

### 3.2 Vercel (frontend)
Set in Vercel dashboard → project → **Settings → Environment Variables**.

| Key | Example | Notes |
|-----|---------|-------|
| `NEXT_PUBLIC_API_BASE_URL` | `https://cli-al-backend.onrender.com` | Browser hits this directly |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` | Same project URL as backend |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_…` | Browser-safe (formerly anon key) |

---

## 4. Cold-start prevention

Render free spins down after 15 min of inactivity, causing ~30s cold starts. We use an external cron service (cron-job.org) to `GET /health` every 5 minutes — GitHub Actions `schedule` is best-effort and was silently skipping runs for 2+ hours at a time, defeating the purpose.

**Current setup (cron-job.org, free tier):**
- URL: `https://cli-al-backend.onrender.com/health`
- Schedule: every 5 minutes
- Notifications: email on failure (3 consecutive failures)

**To reproduce in a fork:**
1. Sign up at https://cron-job.org (free).
2. Create job → URL = `<your-render-url>/health`, schedule = every 5 min, request method = GET.
3. Enable "Notifications" → email on failure.

Any equivalent uptime pinger works (UptimeRobot, BetterStack, Pingdom). The endpoint just needs to be hit before Render's 15-min idle timer fires.

---

## 5. Do not touch without coordination

These files and identifiers are wired into the live deployment. Changing them without updating the corresponding dashboard setting **will take production down**.

| Item | Who depends on it |
|------|------------------|
| `render.yaml` — `rootDir`, `startCommand`, `healthCheckPath` | Render service |
| `/health` endpoint path in `backend/app/routers/health.py` | Render health check + external cron pinger |
| Env var **names** in `backend/app/config.py` (`UPSTAGE_API_KEY`, `SUPABASE_*`, `CORS_ALLOW_ORIGINS`) | Render dashboard values |
| Env var **names** in `frontend/lib/api.ts` (`NEXT_PUBLIC_API_BASE_URL`) | Vercel dashboard values |
| Backend URL registered at cron-job.org | External keepalive pinger (see §4) |

If you must change one of these, update the dashboard side in the same PR and ping the PM in the description.

---

## 6. Adding a new env var

Backend example (e.g., a new `NIM_API_KEY`):
1. Add the field to `backend/app/config.py` (`Settings` class).
2. Add it to `backend/.env.example` and root `.env.example` with a placeholder.
3. Add it to `render.yaml` under `envVars:` with `sync: false`.
4. In Render dashboard → Environment → enter the real value → save → service redeploys.

Frontend example (e.g., a new feature flag exposed to the browser):
1. Prefix with `NEXT_PUBLIC_` to expose it client-side. Without the prefix, only server code sees it.
2. Read it via `process.env.NEXT_PUBLIC_…` in code.
3. Add to `frontend/.env.example`.
4. In Vercel dashboard → Settings → Environment Variables → add for `Production` (and `Preview` if needed) → trigger redeploy.

---

## 7. Rollback

- **Vercel**: Deployments → previous successful deployment → **Promote to Production**.
- **Render**: Service → Events → previous successful deploy → **Rollback to this deploy**.
- **Database schema**: Migrations are applied manually via Supabase SQL Editor; revert by running the inverse SQL.

---

## 8. Cost guardrails (free-tier limits)

| Limit | Mitigation |
|-------|------------|
| Render free: 750 instance-hours/month | One service uses ~720h, well within the cap |
| Supabase free: 500 MB DB, 1 GB storage, **pauses after 7 days of inactivity** | The keepalive pinger only touches the backend, not the DB — watch the Supabase dashboard during long breaks |
| Vercel Hobby: 100 GB bandwidth/month, no commercial use | Sufficient for course demo traffic |
| Upstage: paid per token | Monitor in Upstage Console — not free |

---

## 9. First-time access checklist for a new team member

1. Read this file end-to-end.
2. Get added to the Vercel project, Render service, and Supabase project by the PM.
3. Skim `docs/SETUP.md` and bring up the local dev environment.
4. Open a PR for any change — direct push to `main` is blocked by branch protection.
