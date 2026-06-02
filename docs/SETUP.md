# Local setup

End-to-end instructions to run CLI_AL on a single laptop. Backend + frontend
are local processes; Postgres lives in Supabase cloud (free tier); LLM calls
go to Upstage cloud.

> For the live deployment (Vercel + Render) and the env vars set there,
> see [`DEPLOY.md`](DEPLOY.md). The `.env` files described below only affect
> local dev — never commit real keys, and never edit Render/Vercel dashboard
> values from here.

---

## 0. Prerequisites

| Tool       | Version       | Notes                                    |
| ---------- | ------------- | ---------------------------------------- |
| Python     | 3.11 or newer | `python --version`                       |
| Node.js    | 20 or newer   | `node --version`                         |
| npm        | 10 or newer   | bundled with Node                        |
| (optional) | GNU Make      | macOS/Linux. Windows: use `infra/dev.ps1` |

---

## 1. Get API credentials

### Upstage (Solar Pro 3, Document Parse, Embedding, Groundedness Check)

1. Sign up at https://console.upstage.ai
2. Sidebar → **API Keys** → **Create new secret key**
3. Copy the `up_xxx…` value
4. (Optional) Apply for the AI Initiative program at
   https://www.upstage.ai/ai-initiative for free credits.

### Supabase (Postgres + Auth)

1. Create an account at https://supabase.com
2. **New Project** → name `cli-al` → region `Northeast Asia (Seoul)` → Free
3. Wait ~2 minutes for the project to provision
4. **Project Settings → API Keys**, copy from the *Publishable and secret API keys* tab (NOT the legacy tab):
   - `Project URL` (e.g. `https://abc.supabase.co`)
   - `Publishable key`  (`sb_publishable_…`) — browser-safe
   - `Secret key`       (`sb_secret_…`)      — server-only, bypasses RLS

---

## 2. Apply the database schema

In the Supabase Dashboard → **SQL Editor** → **New query**, paste the contents
of `supabase/migrations/0001_init.sql` and click **Run**. This creates the
`documents`, `rewrites`, and `glossary_cache` tables with RLS policies.

---

## 3. Configure environment files

```bash
cp .env.example .env                      # root (reference only)
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Fill in the real values in `backend/.env` and `frontend/.env.local`. The
backend uses the **secret key** (full DB privileges); the frontend uses only
the **publishable key** plus the public backend URL.

---

## 4. Install dependencies

### macOS / Linux (with `make`)

```bash
cd infra
make install
```

### Windows (PowerShell)

```powershell
pwsh ./infra/dev.ps1 install
```

This runs `pip install -e ".[dev]"` in `backend/` and `npm install` in
`frontend/`.

---

## 5. Run the dev servers

### macOS / Linux

```bash
cd infra
make -j2 dev          # backend on :8000, frontend on :3000
```

Or run them in separate terminals:

```bash
make backend          # one terminal
make frontend         # another terminal
```

### Windows

```powershell
pwsh ./infra/dev.ps1            # spawns two PowerShell windows
# or run each in its own terminal:
pwsh ./infra/dev.ps1 backend
pwsh ./infra/dev.ps1 frontend
```

---

## 6. Smoke test

1. Open http://localhost:3000 — you should see the input page.
2. Click **예시 입력 채우기** to load a sample lease clause.
3. Click **쉬운말로 변환**. Within ~5–15s you should see:
   - Rewritten text with `[1]` `[2]` citation markers
   - Glossary, key-info cards, checklist
   - A coloured groundedness badge top-right
4. Open http://localhost:3000/history — the just-saved entry should appear.
5. Hit http://localhost:8000/health to confirm config flags are `true` for
   Upstage and Supabase.

---

## Troubleshooting

| Symptom                                            | Fix                                                                                            |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `502 LLM 응답 형식 오류`                           | Solar returned non-JSON. Usually transient — retry. Persistent: check `SOLAR_MODEL` is valid.  |
| `health` shows `upstage_configured: false`         | `backend/.env` is missing `UPSTAGE_API_KEY` or wasn't loaded — restart `uvicorn`.              |
| `이력 불러오기 실패`                              | Supabase isn't configured **or** RLS policy blocks it — re-run `0001_init.sql`.                |
| `connect ECONNREFUSED 127.0.0.1:8000`              | Backend isn't running, or `NEXT_PUBLIC_API_BASE_URL` points to the wrong host.                 |
| Tailwind classes look unstyled                     | First run: `cd frontend && npm install` then restart `npm run dev`.                            |
| Solar returns Korean refusal text                  | Input matched the injection / advisory guard — adjust `llm/prompts/rewrite_v2.md` if too strict. |
