# QingQian (青签) · qing_qian

English | [简体中文](README.md)

A web app for drawing and interpreting the **Lü Zu Oracle Lots** (吕祖灵签) — a traditional set of 100 divination lots attributed to Lü Dongbin (吕洞宾), a famous Daoist immortal of the Eight Immortals.

> Design principle: **randomness stays random, lot texts stay canonical, the model only interprets.**
> The lot is drawn server-side with a cryptographically secure RNG; poems, expositions, hexagrams and per-aspect readings come from a fixed lot library; the AI only turns the canonical text into a plain-language reading tailored to your question.
>
> For traditional-culture entertainment only. Please do not take it as advice or superstition.

> Note: the app UI, the AI readings and the in-app assistant are in Chinese, as the product targets a Chinese-speaking audience.

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.10 · FastAPI · SQLAlchemy 2.0 (psycopg2) · OpenAI-compatible SDK |
| Frontend | Vue 3 · Vite · TypeScript · GSAP (temple-inspired UI with micro-animations) |
| Database | PostgreSQL 16 (Docker Compose; tables auto-created on startup) |
| Lot library | `backend/data/lvzu_signs.json` (100 lots, versioned with the repo) |

## Project Layout

```
qing_qian/
├── DESIGN.md                    # Design blueprint (architecture/data/API/AI)
├── docs/                        # Product docs: user guide / FAQ / culture background / admin guide (knowledge base of the in-app assistant)
├── docker-compose.yml           # PostgreSQL 16
├── backend/
│   ├── app/                     # FastAPI app (routers/services/orm)
│   ├── data/lvzu_signs.json     # The 100-lot library (single source of truth)
│   ├── scripts/scrape_zhouyi.py # Lot scraping script (cached, re-runnable)
│   ├── requirements.txt
│   └── .env.example             # Config template
├── frontend/                    # Vue 3 SPA
└── gui-test-screenshots/        # Black-box browser test screenshots (evidence)
```

## Quick Start

**1. Start the database**

```bash
docker compose up -d db        # pgvector/pgvector:pg16 (with vector extension) → localhost:5432
```

**2. Start the backend** (Python 3.10)

```bash
cd backend
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env           # fill in LLM_API_KEY as needed
.venv/bin/uvicorn app.main:app --reload --port 8000
```

**3. Start the frontend**

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173 (vite proxies /api → 8000)
```

## Configuration (`backend/.env`)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Database connection string | the qingqian DB from docker-compose |
| `LLM_API_BASE` | OpenAI-compatible API base | Zhipu `https://open.bigmodel.cn/api/paas/v4` |
| `LLM_API_KEY` | **Required for AI interpretation**; without it, drawing and static lot texts still work | empty |
| `LLM_MODEL` | Model name | `glm-4-flash` |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | Interpretation parameters | 0.8 / 1200 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | **Admin console account** (console API is disabled while the password is empty) | admin / empty |
| `ADMIN_TOKEN_HOURS` | Admin session lifetime (hours) | 12 |
| `USER_SECRET` / `USER_TOKEN_DAYS` | User session signing key / lifetime (days) | empty (sample) / 7 |

**Graceful degradation**: without `LLM_API_KEY`, `/api/interpret` returns 503 with setup hints; the UI hides the entry point and shows a notice — reading lot texts is unaffected. Likewise, if the database is unavailable, drawing still works (just not persisted).

## API Overview

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check (includes LLM configuration status) |
| GET | `/api/signs` | List of the 100 lots |
| GET | `/api/signs/{no}` | Full details of one lot |
| POST | `/api/draw` | Secure random draw → `{drawing_id, sign}` |
| POST | `/api/interpret` | AI interpretation, SSE streaming; follow-ups via `reading_id` + `history` |
| GET | `/api/history` | Current user's draw & interpretation records (**login required**, private) |
| POST | `/api/assistant/chat` | **Usage assistant** chat (SSE, RAG over `docs/`; separate from the interpretation assistant) |
| POST | `/api/assistant/feedback` | Thumbs up / down on assistant answers (1 / -1) |
| POST | `/api/auth/register` | Registration (username + password → token) |
| POST | `/api/auth/login` | **Unified login** (admin/user auto-detected, returns `role`) |
| GET | `/api/auth/me` | Current user profile |
| POST | `/api/admin/users/{id}/reset-password` | Reset a user's password |
| PATCH | `/api/admin/users/{id}/status` | Disable / enable a user |
| GET | `/api/admin/login-logs` | Login / registration events (failures + IP) |
| GET/POST | `/api/admin/kb/status` · `/api/admin/kb/rebuild` | Assistant knowledge-base status / rebuild |
| GET | `/api/admin/assistant-logs` | Assistant Q&A logs with feedback stats |
| POST | `/api/admin/login` | Admin login (token) |
| GET/PUT/POST/DELETE | `/api/admin/*` | Admin: overview / draw records / users / AI settings (Bearer token) |

## Admin Console

Open `/#/admin`; credentials come from `backend/.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) — **change these before any public deployment**.

| Module | Features |
|---|---|
| Overview | Counts (draws / interpretations / follow-ups / users), today's draws, AI config status |
| Draw records | Recent draws & interpretations (paged), deletable (cascades to interpretations and follow-ups) |
| User management | Search, reset password, **disable / enable** (effective immediately), delete; draw counts and last-active time |
| Login logs | Login / registration events (success / failure, reason, IP, device) with a "failures only" filter |
| AI settings | base_url / model / temperature / max tokens / thinking mode / API key — saved to the DB and effective immediately, with a connectivity test |

**Unified login**: admins and regular users share `/#/login`; the backend detects the account type (admin = the single .env account, users = registered accounts).

AI settings live in the DB `settings` table and **take precedence over `.env`**; clearing them falls back to `.env`.

## User Model

| Identity | Visible menu | Behavior |
|---|---|---|
| Guest | Draw · Lot Library · Login / Register | Can draw and interpret immediately; records are **not tied to a person** (admin-visible only), no history page |
| User | Draw · Lot Library · Draw History · account menu | Draws and readings are tied to the account; **history is private** |
| Admin | User menu + Admin | Admin console (separate account, see above) |

- Registration: username (3–32 letters / digits / underscore) + password (≥6 chars); passwords are stored as **PBKDF2-SHA256 with salt**; sessions are HMAC-signed tokens (7 days by default, signed with `USER_SECRET`);
- Draw / interpret / history requests carry the token automatically; guests visiting the history page are guided to login (and redirected back afterwards);
- Login / registration events (including failures) are logged for admins; disabling an account invalidates its token immediately;
- SMS verification is a planned option (requires a messaging provider); the current version is password-only.

## Usage Assistant (QingXiaoQian 青小签)

A floating assistant in the bottom-right corner — a smiling little Daoist-child mascot. It answers questions about using the site and about the cultural background (who Patriarch Lü is, traditional draw etiquette), grounded in the `docs/` knowledge base (SSE streaming; fully separate from the interpretation assistant; a one-time onboarding bubble on first visit).

- **Corpus**: `docs/user-guide.md`, `docs/faq.md`, `docs/lvzu.md` (culture background), `docs/admin-guide.md`; after editing docs, use "Admin → AI settings → Rebuild KB";
- **Q&A logs & feedback**: every exchange is persisted (`assistant_logs`) with 👍/👎 feedback; the admin "Assistant Q&A" page offers a "downvotes only" review, closing the loop docs → answer → feedback → improve docs;
- **Retrieval**: keyword search by default (BM25-style, suited to a small corpus); add an embedding model (e.g. `doubao-embedding-text-240715`) in the console and rebuild to upgrade automatically to **pgvector vector search**;
- The DB image is `pgvector/pgvector:pg16` (vector extension included, data volume compatible).

SSE events: `data: {"delta": "…"}` chunks → `data: {"done": true, "reading_id": …}` → `data: [DONE]`.
Persistence: the first answer is written to `readings`, follow-ups to `messages` (each call records `model` and `prompt_version`).

## Lot Library & Scraping

Source: zhouyi.cc Lü Zu lot detail pages (the classical texts are public domain; the vernacular explanations were compiled from public web pages for internal reference only).

```bash
python3 backend/scripts/scrape_zhouyi.py            # full run (uses the page cache)
python3 backend/scripts/scrape_zhouyi.py --limit 3  # debug
python3 backend/scripts/scrape_zhouyi.py --no-cache # force re-fetch
```

Known source-site gaps (missing upstream, not parsing issues): lot 82's hexagram is merged into its exposition (extracted); lot 97 has no hexagram; lot 90 has no vernacular section and lacks the "行人 / 诉讼" readings.

## Production Mode

The frontend build is served directly by the backend:

```bash
cd frontend && npm run build     # outputs frontend/dist, auto-mounted at FastAPI "/"
```

After that, running only the backend (port 8000) serves both the API and the UI from one origin.

## Test Evidence

`gui-test-screenshots/` holds black-box browser test screenshots: the full draw flow, shake-animation frames, lot detail, lot library search, persisted history, plus mobile narrow-screen and accessibility checks. Issues found and fixed this way include: mis-wrapped vertical poem columns, a too-transparent top bar, mobile top-bar text wrapping, and contrast / keyboard-accessibility problems.

## Compliance

- The site and all AI output carry a "for traditional-culture entertainment only" disclaimer;
- Prompt principles: never rewrite the canonical lot text; no concrete medical / investment / legal advice;
- Before public deployment, replace the vernacular explanations with your own compilation based on public-domain classical texts, and review applicable generative-AI compliance requirements.

## License

- **Code**: MIT (see [LICENSE](LICENSE))
- **Data & content**: see [NOTICE](NOTICE); the vernacular explanations were compiled from public web pages — evaluate or replace them before public use (see Appendix B "Data Source Statement" in [DESIGN.md](DESIGN.md))
