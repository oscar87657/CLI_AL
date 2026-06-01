# [Spring 2026] Algorithms — Term-Project: Team CLI

![Last Commit](https://img.shields.io/github/last-commit/Choroning/CLI_AL)
![Languages](https://img.shields.io/github/languages/top/Choroning/CLI_AL)

This repository hosts **Team CLI**'s term-project for the Spring 2026 Algorithms course at Korea University Sejong — a web-based LLM application powered by **Upstage Solar**, with a **Frontend + Backend** architecture, that intentionally applies algorithm concepts learned in the course.

*Team CLI — Korea University Sejong, Department of Computer Science and Software Engineering — Spring 2026*
<br><br>

## 📑 Table of Contents

- [About This Repository](#about-this-repository)
- [Course Information](#course-information)
- [Team](#team)
- [Project Overview](#project-overview)
- [Algorithm Concepts Applied](#algorithm-concepts-applied)
- [Rewrite Pipeline](#rewrite-pipeline)
- [Frontend UX Features](#frontend-ux-features)
- [Tech Stack](#tech-stack)
- [API Endpoints](#api-endpoints)
- [Database Schema](#database-schema)
- [Environment Variables](#environment-variables)
- [Repository Structure](#repository-structure)
- [Testing](#testing)
- [Deliverables](#deliverables)
- [Roadmap](#roadmap)
- [License](#license)

---


<br><a name="about-this-repository"></a>
## 📝 About This Repository

This repository organizes the source code, documentation, and deliverables for Team CLI's term-project in the Spring 2026 Algorithms course.

> **🤖 AI-Assisted Development**
> This course encourages the use of AI agents.
> A team [Claude Code](https://claude.ai/download) license is provided by the course, and is used actively for coding, refactoring, debugging, testing, and documentation throughout the project.

<br><a name="course-information"></a>
## 📚 Course Information

- **Semester:** Spring 2026 (March – June)
- **Affiliation:** Korea University Sejong

| Course&nbsp;Code| Course            | Type          | Instructor      | Department                              |
|:----------:|:------------------|:-------------:|:---------------:|:----------------------------------------|
|`DCSS309-00`|ALGORITHM|Major Required|Prof. Unggi&nbsp;Lee|Department of Computer Science and Software Engineering|

- **📖 References**

| Type | Contents |
|:----:|:---------|
|Textbook|"Introduction to Algorithms, 3rd Edition" by Cormen, Leiserson, Rivest, and Stein (CLRS)|
|Lecture Notes|[Instructor's Markdown notes and slides (GitHub)](https://github.com/codingchild2424/2026-lecture-algorithm)|
|LLM API|[Upstage Solar — AI Initiative 2025](https://www.upstage.ai/events/ai-initiative-2025-ko)|
|Auxiliary API|NVIDIA NIM (NVIDIA Inference Microservices)|

<br><a name="team"></a>
## 👥 Team

**Team name:** CLI

| Role | Name |
|:-----|:-----|
| Project Manager | Park Cheolwon |
| Backend | Kang Seonguk |
| Frontend | Song Minseong |
| LLM / Prompt Engineering | Kwak Jun |

<br><a name="project-overview"></a>
## 🎯 Project Overview

**행정문서 쉬운말 변환기** — paste or upload an administrative document (lease clause, public notice, government form, contract, etc.) and the service returns a plain-Korean rewrite with citation markers, a glossary of difficult terms, key-info cards (obligations, rights, deadlines), and an action checklist.

### Core Features

1. **Plain-Korean rewriting** of administrative documents with `[1]` `[2]` citation markers tying each claim back to the source.
2. **Structured extraction** — glossary, key-info cards, and action checklist generated alongside the rewrite.
3. **Groundedness check** — every response is scored by Upstage's Groundedness API and surfaced as a coloured badge so users know when to double-check the original.

### Demo

- Live: https://cli-al.vercel.app
- API: https://cli-al-backend.onrender.com/health

<br><a name="algorithm-concepts-applied"></a>
## 🧠 Algorithm Concepts Applied

All five concepts are implemented in [`Backend/app/services/algorithms.py`](Backend/app/services/algorithms.py) and called from [`Backend/app/services/rewrite_service.py`](Backend/app/services/rewrite_service.py) as part of the `/rewrite` response pipeline.

| Concept | CLRS | Where it is used | Complexity | Notes |
|:--------|:----:|:-----------------|:----------:|:------|
| **Hash Table — Chaining** | Ch. 11.2 | `HashTableChaining` + `dedup_glossary` in `algorithms.py`; called in `rewrite_service.py` after glossary parsing | O(1) avg insert/lookup | Polynomial rolling hash `h = (h·131 + ord(c)) mod m`; handles arbitrary Unicode (Korean). Removes duplicate glossary terms the LLM may emit before any further processing. |
| **Merge Sort** | Ch. 2.3 | `merge_sort_glossary` in `algorithms.py`; called in `rewrite_service.py` after dedup | Θ(n log n) | Stable sort — equal terms preserve their original relative order. Sorts the deduplicated glossary alphabetically (case-insensitive) so the UI renders a consistent dictionary-style list. |
| **Counting Sort** | Ch. 8.2 | `counting_sort_checklist` in `algorithms.py`; called in `rewrite_service.py` after checklist parsing | Θ(n + k), k = 3 | Sorts checklist items by priority (high → medium → low). k is bounded at 3, so this runs in linear time. Stable: items with the same priority keep their LLM-output order. |
| **Dynamic Programming — LCS** | Ch. 15.4 | `lcs_word_ratio` in `algorithms.py`; called in `rewrite_service.py` after the LLM rewrite | O(mn) time, O(n) space | Word-tokenised LCS between the original document and the plain-Korean rewrite. Normalised to [0, 1] as `LCS_length / max(|original|, |rewrite|)`. Returned as `preservation_ratio` in the API response alongside the Upstage Groundedness label, giving a purely local, deterministic measure of content fidelity. Space-optimised to two rolling rows instead of the full O(mn) table. |
| **Graph — BFS** | Ch. 22.1–22.2 | `build_term_graph` + `bfs_related_terms` in `algorithms.py`; called in `rewrite_service.py` after glossary is finalised | O(V + E) | Builds a directed adjacency list where an edge A → B exists when term B appears in the definition of term A (i.e., understanding A requires knowing B). BFS from each term discovers all transitively related terms. Results are attached to each `GlossaryTerm` as `related_terms` in the API response. |

<br><a name="rewrite-pipeline"></a>
## 🔁 Rewrite Pipeline

`POST /rewrite` calls Upstage Solar three times in series, then post-processes the structured fields with the CLRS algorithms:

1. **Call 0 — Relevance Check** ([`llm/prompts/relevance_check_v1.md`](llm/prompts/relevance_check_v1.md))
   Classifies whether the input is an administrative document / public notice / 약관 / 계약서. If `is_relevant: false`, the service short-circuits with a guidance message and **skips history persistence** so unrelated text never pollutes the history list.

2. **Call 1 — Plain-Korean Rewrite + Citations** ([`llm/prompts/rewrite_v2.md`](llm/prompts/rewrite_v2.md))
   Hybrid RAG (lexical + semantic, [`backend/app/rag/`](backend/app/rag/)) over [`llm/corpus/rag_seed.jsonl`](llm/corpus/rag_seed.jsonl) (법제처 어려운 표현 정비 사례) retrieves up to 3 supporting chunks, which are injected into the prompt. The model emits the rewrite with `[1]` `[2]` citation markers tying each claim back to a span.

3. **Call 2 — Structured Extraction** ([`llm/prompts/analysis_v1.md`](llm/prompts/analysis_v1.md))
   Given the original + rewrite, Solar extracts the glossary, key-info cards, and checklist as a single JSON response.

After the three calls:
- Upstage **Groundedness Check** scores the rewrite against the original; we surface the label + a coloured badge.
- The CLRS algorithms post-process the structured fields (see [Algorithm Concepts Applied](#algorithm-concepts-applied)).
- The CLRS DP-LCS yields a deterministic `preservation_ratio` alongside Groundedness.

Rate limit: 10 requests / minute / IP (`RateLimiter` in [`backend/app/services/rate_limit.py`](backend/app/services/rate_limit.py)).

<br><a name="frontend-ux-features"></a>
## ✨ Frontend UX Features

- **Full-viewport snap sections** — Landing has 3 snap sections; the convert result is also split into 3 (input → rewrite + citations → key info / glossary / checklist + embedded footer). Custom GSAP-based scroll snap with intra-box scroll lock (so scrolling inside a panel never accidentally jumps sections).
- **Citation-marker sync** — As the user scrolls the rewrite, the citation panel snaps to the matching `[N]` item, and both the in-text marker and the citation chip are highlighted in primary.
- **Accessibility panel** (bottom-right toggle, mobile + desktop)
  - 3-step font size (`html.size-l` / `html.size-xl`)
  - Dark mode (`.dark` class + CSS variable token swap)
  - Dyslexia assist — OpenDyslexic font + site-wide Bionic Reading (bold word heads via React-rendered `<b class="bx">`)
- **Result copy** — Clean plain-text export with Korean labels (중요/보통/참고, 근거 충분/부족/불확실, …) instead of raw enum codes.
- **Result print** — Dedicated `PrintDoc` (semantic HTML document) renders for `@media print` instead of screen-capturing the page.
- **History restore** — `/convert?id=<rewrite_id>` re-hydrates a saved result without re-calling the LLM.
- **Irrelevant-input notice** — If Call 0 classifies the input as non-administrative, the result section is suppressed and a compact notice appears in the input area; nothing is saved to history.
- **First-visit disclaimer** — Legal-notice modal gated by `localStorage`.

<br><a name="tech-stack"></a>
## 🛠 Tech Stack

| Layer | Choice |
|:------|:-------|
| Frontend | Next.js 15 (App Router, React 19) + Tailwind CSS |
| Backend | FastAPI + uvicorn (Python 3.11) |
| Database / Auth | Supabase (Postgres, free plan) |
| LLM | Upstage Solar Pro 2 (rewrite, glossary, key-info), Document Parse, Groundedness Check |
| External APIs | 국가법령정보센터 Open API (legal term lookup via `GET /law/term`) |
| Frontend hosting | Vercel (Hobby plan) |
| Backend hosting | Render (free plan, Singapore) |
| Cold-start mitigation | External cron pinger (cron-job.org, every 5 min) on `/health` |

See [`docs/DEPLOY.md`](docs/DEPLOY.md) for the deployment topology and operational notes.


<br><a name="api-endpoints"></a>
## 🔌 API Endpoints

Backend (FastAPI). Production base URL: `https://cli-al-backend.onrender.com`.

| Method | Path | Purpose |
|:------:|:-----|:--------|
| GET | `/health` | Health probe. Returns `{status, upstage_configured, supabase_configured, law_configured, model}` so deploy gates can verify env wiring. |
| POST | `/parse` | File → text. `multipart/form-data` (PDF · TXT · DOCX · HWPX, ≤10MB). |
| POST | `/rewrite` | Main entry. Body `{text, save_history}` → `RewriteResponse` (rewrite + citations + glossary + key_info + checklist + groundedness + preservation_ratio + summary + relevance + document_id). Rate-limited 10/min. |
| GET | `/history?limit=N` | Most recent rewrites (max 100), with previews. |
| GET | `/history/{rewrite_id}` | Full restore payload for a single rewrite (used by `/convert?id=...`). |
| DELETE | `/history/{rewrite_id}` | Deletes the parent `documents` row (cascades to `rewrites`). |
| GET | `/law/term?q=...` | (Optional) 국가법령정보센터 OPEN API passthrough. Returns 503 if `LAW_API_KEY` is unset. |

<br><a name="database-schema"></a>
## 🗄 Database Schema (Supabase / Postgres)

Three tables, created by [`supabase/migrations/0001_init.sql`](supabase/migrations/0001_init.sql):

- **`documents`** — Original input texts. `id` (uuid pk), `original_text`, `source`, `metadata` (jsonb), `created_at`.
- **`rewrites`** — Structured rewrite results, FK to `documents` with `ON DELETE CASCADE`. Columns: `rewrite_text`, `citations` (jsonb), `glossary` / `key_info` / `checklist` (jsonb), `groundedness_label`, `groundedness_badge`, `prompt_version`, `model`.
- **`glossary_cache`** *(future)* — Term → definition cache for the RAG path.

RLS is on for all three. Anonymous **read** is allowed (history page reads directly); writes are routed through the backend `service_role`, which bypasses RLS. Deleting a history entry deletes the parent `documents` row, cascading to its `rewrites`. Irrelevant inputs (Call 0 `is_relevant=false`) are never persisted.

<br><a name="environment-variables"></a>
## 🔑 Environment Variables

| Scope | Variable | Required | Purpose |
|:-----:|:---------|:--------:|:--------|
| backend | `UPSTAGE_API_KEY` | ✅ | Solar Pro 2 · Document Parse · Groundedness Check |
| backend | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | ✅ | Backend persistence (bypasses RLS) |
| backend | `CORS_ALLOW_ORIGINS` | ✅ | Comma-separated allowed frontend origins |
| backend | `SOLAR_MODEL` | ⬜ | Override the Upstage model id |
| backend | `LAW_API_KEY` | ⬜ | 국가법령정보센터 OPEN API key (enables `/law/term`) |
| frontend | `NEXT_PUBLIC_API_BASE_URL` | ✅ | Backend base URL (e.g. `http://localhost:8000`) |
| frontend | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | ⬜ | Browser-safe Supabase access (read-only) |

See [`docs/SETUP.md`](docs/SETUP.md) for full local setup; [`docs/DEPLOY.md`](docs/DEPLOY.md) for Vercel/Render production configuration.

<br><a name="repository-structure"></a>
## 🗂 Repository Structure

```
CLI_AL/
├── backend/             FastAPI app (uvicorn entry: app.main:app)
│   ├── app/
│   │   ├── main.py      App factory + CORS
│   │   ├── config.py    pydantic-settings (UPSTAGE_*, SUPABASE_*, CORS_*, LAW_API_KEY)
│   │   ├── models/      pydantic schemas (RewriteRequest/Response, RelevanceResult, …)
│   │   ├── routers/     /health · /parse · /rewrite · /history · /law
│   │   ├── services/    upstage_client · supabase_client · rewrite_service · history_service ·
│   │   │                law_client · algorithms · prompt_loader · rate_limit · cache_service
│   │   └── rag/         Hybrid RAG (store · indexer · retriever · db) over llm/corpus
│   ├── tests/           pytest (test_health · test_prompt_loader)
│   ├── scripts/         build_rag_seed.py — RAG seed builder
│   └── pyproject.toml
├── frontend/            Next.js (App Router, React 19, "use client" pages)
│   ├── app/             layout.tsx · page.tsx (landing) · convert/page.tsx · history/page.tsx
│   ├── components/      Dropzone · RewriteText · CitationsPanel · KeyInfoCards · GlossaryList ·
│   │                    Checklist · ResultActions · AccessibilityBar · DisclaimerModal · …
│   ├── lib/             api.ts (FastAPI client) · useScrollSnap.ts · Bionic.tsx · dyslexiaBionic.ts
│   └── package.json
├── llm/
│   ├── prompts/         relevance_check_v1 · rewrite_v2 · analysis_v1
│   └── corpus/          rag_seed.jsonl — 법제처 어려운 표현 정비 사례 (RAG seed)
├── supabase/migrations/ 0001_init.sql (documents · rewrites · glossary_cache + RLS policies)
├── infra/               Makefile + dev.ps1 for local two-server bring-up
├── docs/                SETUP.md (local dev) · DEPLOY.md (production)
├── .github/             CODEOWNERS
└── render.yaml          Render Blueprint (backend service definition)
```

<br><a name="testing"></a>
## ✅ Testing

- **Backend** — `cd backend && pytest -q` (current suites: `test_health.py`, `test_prompt_loader.py`). Add new tests under `backend/tests/`.
- **Frontend** — `cd frontend && npx tsc --noEmit` for a fast type-check, or `npm run build` for the full Next.js production build (also type-checks).
- **Combined** — `cd infra && make typecheck` runs both `mypy backend` and `tsc --noEmit` for the frontend.

CI hook: every commit pushed to `main` is built by Vercel (frontend) and Render (backend, via [`render.yaml`](render.yaml) Blueprint autoDeploy). Failed builds block the deploy and surface on the commit's GitHub status.

<br><a name="deliverables"></a>
## 📦 Deliverables

| # | Deliverable | Description | Status |
|:-:|:------------|:------------|:------:|
| 1 | Application | Working product + full source code (this repository) | MVP deployed |
| 2 | Technical Report | System architecture, tech stack, LLM usage, key implementation details, limitations | Pending |
| 3 | Development Process Document | Planning → scheduling → execution → retrospective; meeting notes, timelines, per-role progress, issue tracking | Pending |
| 4 | Presentation Slides | Final presentation deck — **in English** | Pending |

> The final presentation will take place during class. **Both the slides and the presentation itself must be in English.**

<br><a name="roadmap"></a>
## 🗺 Roadmap

- [x] Team formed
- [x] Public GitHub repository created
- [x] Initial topic statement (one-paragraph summary + 3 core features)
- [x] Upstage Solar API approved
- [ ] NVIDIA NIM access (optional)
- [x] Claude Code 1-month license assigned to team representative
- [x] Proposal
- [x] Prototype
- [x] MVP — deployed to Vercel + Render
- [ ] Feature polish
- [ ] Technical report
- [ ] Development process document
- [ ] Presentation slides

<br><a name="license"></a>
## 🤝 License

This repository is released under the [MIT License](LICENSE).

---
