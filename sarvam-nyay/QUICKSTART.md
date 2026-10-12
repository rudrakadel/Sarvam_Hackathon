# Quick Start — VeriDictum AI

Up and running in **under 10 minutes** with SQLite + no paid APIs.

For full production deployment (PostgreSQL, Celery, Docker), see
[`DEPLOYMENT.md`](DEPLOYMENT.md).

---

## 1. Prerequisites

| Tool                      | Version    | Check                       |
| ------------------------- | ---------- | --------------------------- |
| Python                    | 3.12+      | `python --version`          |
| Node.js                   | 20+        | `node --version`            |
| npm                       | 10+        | `npm --version`             |
| Git                       | any recent | `git --version`             |
| (Optional) Docker         | 24+        | `docker --version`          |

External AI keys are **not required for the demo seed** — `seed_screenshots.py`
inserts static, FK-coherent demo data without calling OpenAI / DeepInfra / Azure.
You only need real keys to exercise the live pipelines (upload an audio file
and trigger Whisper transcription, for example).

---

## 2. Clone and configure

```bash
git clone <repo-url>
cd project_01_veridictum
```

### Backend env

```bash
cd backend
cp .env.example .env

# Generate a strong SECRET_KEY and append it to .env:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

`backend/.env.example` already defaults `DATABASE_URL` to
`sqlite+aiosqlite:///./veridictum.db` so the demo runs entirely on SQLite.

### Frontend env

```bash
cd ../frontend
cp .env.example .env
# .env already points VITE_API_URL at http://localhost:8000/api/v1
```

---

## 3. Backend bring-up

### 3.1 Virtualenv

```bash
cd ../backend
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3.2 Seed the demo

The seeder creates the database schema and 15 cases with full demo evidence.
**No migrations or `alembic upgrade` required for SQLite** — the seeder
calls `Base.metadata.create_all()` itself.

```bash
python seed_screenshots.py --fresh
```

Expected tail of the output:

```
Seed complete.
  organisation : Blackwood & Associates
  persona      : Sarah Blackwood (admin@blackwoodlaw.com / Demo@Pass123!)
  qa user      : qa.tester@gmail.com / QATest2026!Secure (when present)
  cases        : 15
  contradictions inserted on lead case : 3
  total contradictions : 6
  reports      : 6
```

### 3.3 Start the API

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is now at `http://localhost:8000`:

- **Swagger UI**: `http://localhost:8000/docs`
- **Health check**: `http://localhost:8000/health`

> **Pick one** of `127.0.0.1` or `localhost` and stick with it for both the
> frontend URL and your browser, otherwise CORS will reject the preflight.
> The defaults are configured for `localhost`.

---

## 4. Frontend bring-up

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server starts at `http://localhost:5173`.

Visit it, then sign in with the seeded persona:

| Email                     | Password         | Role  |
| ------------------------- | ---------------- | ----- |
| `admin@blackwoodlaw.com`  | `Demo@Pass123!`  | ADMIN |

---

## 5. What you should see

After signing in:

- **Dashboard** — 15 cases, 6 contradictions (with severity stack `2 critical · 3 high · 1 medium`), 16 documents, 21 audio files. 2 critical contradictions alert banner.
- **Cases list** — all 15 cases with status pills (13 OPEN, 2 IN_REVIEW).
- **People v. Marcus Whitfield** → 4 audio recordings (all unique names), 2 documents, and **3 real contradictions** on the Contradictions tab.
- **Ask AI** — 2 seeded Q&A pairs with proper citation chips like
  `Doc · p. 3` and `Marcus Whitfield · 2:14`.
- **Reports** — 6 reports across 5 cases (2 COMPLETE downloadable, 2 GENERATING, 2 QUEUED).

If anything is empty or zero, the seeder didn't run or the API can't reach
the database. Check the bottom of `backend/.env` for the `DATABASE_URL` and
that `backend/veridictum.db` exists.

---

## 6. Optional: production-grade PostgreSQL

The demo runs on SQLite but the production schema (triggers, GIN FTS,
composite indexes, CHECK constraints) is PostgreSQL-only. To exercise it
locally:

```bash
# Start a Postgres 16 container:
docker run --name veridictum-pg \
    -e POSTGRES_USER=veridictum \
    -e POSTGRES_PASSWORD=veridictum \
    -e POSTGRES_DB=veridictum \
    -p 5432:5432 -d postgres:16

# Switch backend/.env:
#   DATABASE_URL=postgresql+asyncpg://veridictum:veridictum@localhost:5432/veridictum
#   SYNC_DATABASE_URL=postgresql+psycopg2://veridictum:veridictum@localhost:5432/veridictum

# Run migrations (NOT just seed):
alembic upgrade head

# Then seed:
python seed_screenshots.py --fresh
```

Migration `0003` will install the `set_updated_at()` trigger, the GIN FTS
indexes, the composite indexes, and the CHECK constraints. On SQLite that
same migration silently no-ops.

---

## 7. Optional: Celery + Redis (real async pipelines)

The demo seed inserts pre-computed evidence; you don't need Celery or Redis
to log in and click around. You only need them if you want to upload an audio
file and watch Whisper transcription happen.

```bash
# Redis (Docker)
docker run --name veridictum-redis -p 6379:6379 -d redis:7

# In separate terminals:
celery -A app.tasks.celery_app worker -Q transcription -c 2 -n transcription@%h
celery -A app.tasks.celery_app worker -Q ocr           -c 4 -n ocr@%h
celery -A app.tasks.celery_app worker -Q analysis      -c 2 -n analysis@%h
celery -A app.tasks.celery_app worker -Q reports       -c 2 -n reports@%h
```

You will also need real `OPENAI_API_KEY` / `DEEPINFRA_API_KEY` /
`AZURE_DOC_INTELLIGENCE_*` values in `.env` for the pipelines to actually run.

---

## 8. Run the test suite

```bash
cd backend
pytest -v
# Expected: 52 / 52 passed in ~22s
```

The suite runs on an in-memory SQLite DB — no external services, no Redis,
no Celery broker.

---

## 9. Build the frontend for production

```bash
cd frontend
npm run build
# Output: dist/
npx vite preview --host localhost --port 5173
```

`npm run build` runs `tsc` (strict mode) followed by `vite build`. Both
must complete with zero errors.

---

## 10. Troubleshooting

| Symptom                                                | Cause / Fix                                                                 |
| ------------------------------------------------------ | --------------------------------------------------------------------------- |
| `pysqlite is not async`                                | `DATABASE_URL` is `sqlite://...`. Change to `sqlite+aiosqlite:///...`.      |
| Dashboard shows zeros after login                      | Frontend origin doesn't match `ALLOWED_ORIGINS`. Use `http://localhost:5173`, NOT `127.0.0.1`. |
| `401 Unauthorized` on every request                    | The `SECRET_KEY` changed since you logged in. Log out and back in.          |
| `pytest` collects 0 tests                              | You're outside `backend/`. Run `pytest` from `backend/`.                    |
| Contradictions tab is empty on Whitfield               | You skipped step 3.2 or ran the old `seed_demo.py`. Run `seed_screenshots.py --fresh`. |
| `npm run dev` fails to install                         | Node 18 is too old for some transitive deps. Upgrade to Node 20+.           |
| WebSocket connection drops repeatedly                  | Browser is hitting `ws://127.0.0.1:8000` but the backend is on `localhost`. Match the hostnames. |
| `bcrypt` warning during seed                           | passlib + bcrypt 4 quirk. Harmless. Hashing still works.                    |
| Want a fresh DB                                        | Delete `backend/veridictum.db` and re-run `seed_screenshots.py --fresh`.    |
