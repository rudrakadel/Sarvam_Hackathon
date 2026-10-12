# Architecture — VeriDictum AI

> Enterprise legal-AI platform that ingests courtroom audio + documents,
> detects factual contradictions, and answers natural-language questions
> about case evidence with citation-anchored RAG.

This document is the single source of truth for *how* the system is built.
For *what* the system does, see `README.md`. For *how to run it*, see
`QUICKSTART.md` and `DEPLOYMENT.md`.

---

## 1. System diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                                Browser                                     │
│  React 18 SPA · Vite 5 · TypeScript · Tailwind · TanStack Query · Zustand  │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │  HTTPS (REST + WebSocket)
                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend  (port 8000)                         │
│                                                                            │
│   Middleware stack:                                                        │
│     [ CORS · TrustedHost · Request-ID · structlog · Security headers ]     │
│                                                                            │
│   Routers (api/v1/):                                                       │
│     auth · users · cases · audio · documents · contradictions ·            │
│     query · reports · dashboard · notifications                            │
│                                                                            │
│   Services:                                                                │
│     query_service (3-pass RAG) · courtroom_audit_analyzer ·                │
│     courtroom_brief_pdf_service                                            │
└──┬───────────────┬────────────────┬───────────────────────────┬────────────┘
   │               │                │                           │
   ▼               ▼                ▼                           ▼
┌──────────┐  ┌──────────┐  ┌──────────────┐         ┌──────────────────────┐
│ Postgres │  │  Redis   │  │   Celery     │         │ External AI services │
│   16     │  │          │  │   workers    │         │                      │
│          │  │ • Cache  │  │              │  ◄────► │ • OpenAI (analysis)  │
│ • Tables │  │ • Queue  │  │ • transcribe │         │ • DeepInfra (Whisper)│
│ • Enums  │  │ • Pub/Sub│  │ • ocr        │         │ • Azure DI (OCR)     │
│ • Trigger│  │ • Sessions│ │ • analyze    │         │ • Pinecone (vectors) │
│ • GIN FTS│  │          │  │ • report     │         │ • Azure Blob (files) │
└──────────┘  └──────────┘  └──────────────┘         └──────────────────────┘
```

Async paths (long-running):

```
upload   →  POST /audio                          (returns 202)
         →  AudioFile row + Celery task          (transcribe queue)
         →  Whisper v3 → transcript_segments
         →  Redis pub/sub event
         →  WebSocket fan-out → frontend updates
```

Analysis path:

```
POST /contradictions/analyze                      (returns 202 + job_id)
   → Celery analysis queue
   → GPT-4.1-nano (structured-output JSON mode)
   → contradictions[] (status = AI_SUGGESTED)
   → notification fired via WebSocket
```

---

## 2. Tech stack

| Layer            | Technology                                                  |
| ---------------- | ----------------------------------------------------------- |
| **Backend**      | Python 3.12 · FastAPI · async SQLAlchemy 2.0 · Alembic      |
| **Database**     | PostgreSQL 16 (prod) · SQLite + aiosqlite (tests, local dev)|
| **Queue**        | Redis 7 · Celery 5 (4 dedicated worker pools)               |
| **AI: STT**      | DeepInfra Whisper Large v3 + speaker diarization            |
| **AI: OCR**      | Azure Document Intelligence `prebuilt-read`                 |
| **AI: Analysis** | OpenAI GPT-4.1-nano (structured-output JSON mode)           |
| **Vector search**| Pinecone (OpenAI `text-embedding-3-small`) → PG FTS fallback|
| **Blob storage** | Azure Blob (audio, documents, signed PDF reports)           |
| **PDF**          | ReportLab                                                   |
| **Auth**         | JWT HS256 (15-min access / 7-day refresh) · bcrypt · TOTP   |
| **Frontend**     | React 18 · TypeScript · Vite 5 · Tailwind · TanStack Query  |
| **State**        | Zustand (localStorage persist)                              |
| **Forms**        | React Hook Form + Zod                                       |
| **Real-time**    | WebSockets (FastAPI) + Redis pub/sub fan-out                |
| **Observability**| structlog JSON logs + Request-ID + `X-Process-Time` header  |
| **Containers**   | Docker + Compose (8 services)                               |
| **Testing**      | pytest + pytest-asyncio (SQLite in-memory)                  |

---

## 3. Backend module map

```
backend/app/
├── api/
│   ├── deps.py                # FastAPI deps: db, current user, rate limit
│   └── v1/
│       ├── auth.py            # Register, login, refresh, MFA, sessions
│       ├── users.py           # GET /users/me, organisation members
│       ├── cases.py           # CRUD, members, audit log
│       ├── audio.py           # Upload audio → Celery transcribe task
│       ├── documents.py       # Upload PDF → Celery OCR task
│       ├── contradictions.py  # Analyze, list, summary/stats, review
│       ├── query.py           # POST /query  ·  GET /query/history
│       ├── reports.py         # Generate + download PDF reports
│       ├── dashboard.py       # Org-wide aggregated stats
│       ├── notifications.py   # In-app inbox
│       └── _phase_bc_endpoints.py  # Courtroom audit + brief PDF
│
├── models/                    # SQLAlchemy ORM
│   ├── user.py                # Organisation, User, RefreshToken, Invitation
│   ├── case.py                # Case, CaseMember
│   ├── evidence.py            # AudioFile, Transcript, TranscriptSegment, Document, DocumentPage
│   ├── contradiction.py       # Contradiction, AnalysisJob, Report, NLQuery, AuditLog
│   └── notification.py        # Notification
│
├── schemas/                   # Pydantic v2 request/response shapes
│
├── services/
│   ├── query_service.py       # 3-pass RAG retrieval engine
│   ├── courtroom_audit_analyzer.py
│   └── courtroom_brief_pdf_service.py
│
├── tasks/
│   ├── transcription.py       # DeepInfra Whisper → segments + tsvector index
│   ├── ocr.py                 # Azure DI → per-page text + confidence
│   ├── contradiction.py       # GPT-4.1-nano structured contradiction detection
│   └── report.py              # ReportLab PDF + Azure Blob upload + SAS URL
│
├── utils/                     # security (bcrypt, JWT), azure_blob, email
│
├── websocket/
│   ├── manager.py             # WebSocket connection manager + auth
│   └── pubsub.py              # Redis pub/sub bridge — fans out to all connections
│
├── config.py                  # Pydantic Settings — every env var typed + validated
├── database.py                # Async engine, session factory, UUIDString / JSONText
└── main.py                    # FastAPI app, middleware, lifespan
```

---

## 4. Frontend module map

```
frontend/src/
├── App.tsx                                # Router + QueryClient + ErrorBoundary
├── main.tsx                               # Vite entry
│
├── components/
│   ├── atoms/                             # Button, Input, Badge
│   ├── molecules/                         # (future composed widgets)
│   └── organisms/
│       ├── Layout.tsx                     # Sidebar + Topbar (active-state accent rail)
│       └── ErrorBoundary.tsx              # Render-error recovery surface
│
├── pages/
│   ├── auth/                              # Login, Register, Forgot, Reset
│   ├── dashboard/                         # KPIs · severity stack · queue panel
│   ├── cases/                             # List · Detail (6 tabs) · New
│   ├── transcripts/                       # Audio upload, transcript viewer
│   ├── documents/                         # Document upload
│   ├── reports/                           # NL Query · Reports list
│   └── settings/                          # Profile · Password · MFA · Sessions
│
├── services/
│   └── api.ts                             # Axios with JWT auto-refresh interceptor
│
├── store/
│   └── authStore.ts                       # Zustand persisted auth (localStorage)
│
├── hooks/                                 # useWebSocket etc.
├── types/                                 # TS interfaces mirroring backend schemas
└── utils/                                 # format(timestamp, response time, user-agent)
```

---

## 5. Database

### Schema

PostgreSQL 16 (prod). The full DDL is in
`backend/alembic/versions/0001_initial_schema.py` plus
`0002_add_notifications.py` plus `0003_perf_triggers_fts.py`.

```
organisations ──┬── users ──┬── refresh_tokens
                │           ├── user_sso_links
                │           ├── invitations
                │           └── notifications
                │
                └── cases ──┬── case_members
                            ├── audio_files ── transcripts ── transcript_segments
                            ├── documents ── document_pages
                            ├── contradictions  ──  analysis_jobs
                            ├── reports
                            ├── nl_queries
                            └── audit_logs
```

Every table uses UUID primary keys (`gen_random_uuid()` server default on
Postgres, `str(uuid.uuid4())` on SQLite via the `UUIDString` TypeDecorator).
Every parent → child relationship cascades on delete except where business
rules require `ON DELETE SET NULL` (e.g. `audit_logs.user_id` and
`analysis_jobs.triggered_by_id` — the records survive the user being
removed).

### Triggers (PostgreSQL)

Migration `0003` installs a generic `set_updated_at()` PL/pgSQL function and
attaches a row-level `BEFORE UPDATE` trigger to every table with an
`updated_at` column. This means the timestamp is authoritative even for
direct SQL updates that bypass SQLAlchemy.

```sql
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### Full-text search (PostgreSQL)

Migration `0003` adds a `STORED GENERATED` tsvector column on
`transcripts.full_text` and `documents.extracted_text`, plus a GIN index over
each. The 3-pass RAG engine's "Pass 2" (PostgreSQL FTS) uses
`plainto_tsquery` against these indexes.

```sql
ALTER TABLE transcripts
ADD COLUMN full_text_tsv tsvector
GENERATED ALWAYS AS (to_tsvector('english', coalesce(full_text, ''))) STORED;

CREATE INDEX ix_transcripts_full_text_gin ON transcripts USING GIN (full_text_tsv);
```

### Composite indexes (hot paths)

| Index                                       | Backs                                          |
| ------------------------------------------- | ---------------------------------------------- |
| `cases (organisation_id, status)`           | Cases list filter                              |
| `contradictions (case_id, severity)`        | Severity stack on case header                  |
| `contradictions (case_id, status)`          | Pending-review filter                          |
| `audio_files (case_id, status)`             | Processing-queue dashboard panel               |
| `documents (case_id, status)`               | Processing-queue dashboard panel               |
| `reports (case_id, status)`                 | Reports tab on case detail                     |
| `notifications (user_id, is_read, created_at DESC)` | Notification inbox ordered by recency  |
| `audit_logs (organisation_id, case_id, created_at)` | Audit log read paths (from `0001`)     |

### CHECK constraints

| Constraint                                       | Enforces                              |
| ------------------------------------------------ | ------------------------------------- |
| `ck_contradictions_confidence_range`             | `confidence_score ∈ [0, 1]`           |
| `ck_documents_avg_confidence_range`              | `avg_confidence ∈ [0, 1]` or NULL     |
| `ck_contradictions_document_page_positive`       | `document_page > 0` or NULL           |
| `ck_audio_files_size_nonneg`                     | `file_size_bytes >= 0`                |
| `ck_documents_size_nonneg`                       | `file_size_bytes >= 0`                |

### Portability layer

`backend/app/database.py` defines two custom SQLAlchemy types:

- `UUIDString` — stores UUIDs as `VARCHAR(36)` on every backend. SQLite can't
  do native UUIDs and the test suite still needs to run, so we trade a few
  bytes of storage for portability. Postgres uses native `UUID` in the
  migration but the ORM-level type accepts both.
- `JSONText` — stores dicts/lists as JSON text. Postgres normally gets JSONB
  via dialect-specific columns in the migration, but for ORM-side
  declarations this gives us a single field type that works everywhere.

---

## 6. Authentication flow

```
1. POST /auth/login  { email, password }
   ↓
2. bcrypt.checkpw → user lookup → if mfa_enabled → 202 + { mfa_required: true }
                                  else                → 200 + { access_token, refresh_token }
   ↓
3. POST /auth/verify-mfa  { totp_code }           (only if step 2 returned mfa_required)
   ↓
4. Frontend stores tokens in Zustand → persist → localStorage
   ↓
5. Axios request interceptor attaches Authorization: Bearer <access>
   ↓
6. On 401, axios response interceptor calls POST /auth/refresh once and
   replays the original request. Concurrent 401s queue behind a single
   refresh and resolve as a batch.
   ↓
7. POST /auth/logout revokes the refresh token (server-side) and the
   Zustand store clears localStorage.
```

Refresh tokens are stored hashed (`bcrypt`) so a stolen DB row can't be
replayed.

---

## 7. AI pipeline: contradiction detection

```
1. Attorney uploads WAV / MP3 / M4A to POST /api/v1/cases/{id}/audio
   → 202 + audio_id; file streamed to Azure Blob; Celery transcription task enqueued.

2. transcription worker pulls from queue
   → DeepInfra Whisper Large v3 with diarization
   → builds transcript_segments rows (speaker, start, end, text, confidence)
   → full_text column on transcripts is populated
   → Postgres trigger maintains the tsvector column for FTS
   → Redis pub/sub: "transcript_ready" → WebSocket fan-out → UI updates

3. Attorney uploads PDF to POST /api/v1/cases/{id}/documents
   → Celery OCR task enqueued
   → Azure Document Intelligence (prebuilt-read) → document_pages with bbox + confidence
   → avg_confidence rolled up on documents
   → Pub/sub: "ocr_complete"

4. Attorney triggers POST /api/v1/cases/{id}/contradictions/analyze
   → AnalysisJob row created (status QUEUED)
   → Celery analysis worker:
     - Fetches all transcripts + documents for the case
     - Calls GPT-4.1-nano with structured-output JSON mode
     - Validates response against Pydantic schema before insert
     - Writes contradictions[] (status = AI_SUGGESTED)
   → Pub/sub: "analysis_complete" → toast + badge update

5. Attorney reviews each card → PATCH /contradictions/{id}/review
   → status transitions to CONFIRMED or REJECTED
   → reviewed_by_id + reviewed_at + optional attorney_notes
   → audit_log row appended (immutable, 7-year retention)
```

---

## 8. 3-pass RAG query engine

When a user asks `POST /api/v1/cases/{id}/query`:

| Pass | Strategy                                    | Backed by                       |
| ---- | ------------------------------------------- | ------------------------------- |
| 1    | Vector search                               | Pinecone + OpenAI embeddings    |
| 2    | PostgreSQL native FTS (`plainto_tsquery`)   | GIN tsvector indexes (mig 0003) |
| 3    | Keyword `ILIKE` on individual query terms   | Trigram-tolerant                |
| 0    | Fallback: full case corpus to GPT           | Always non-empty                |

GPT-4.1-nano then synthesises an answer and emits inline source tokens
(`[SOURCE: type=transcript, speaker=…, timestamp=…]`). The backend parses
those tokens into a structured `citations[]` array stored on the `NLQuery`
row. The frontend renders each as a chip:

- `Marcus Whitfield · 2:14` (audio)
- `Doc · p. 3` (document)

---

## 9. Real-time architecture

```
Celery worker  ──[publishes]──►  Redis channel "veridictum:events"
                                          │
                                          ▼
                              redis_pubsub_listener (FastAPI startup task,
                              now wired via `lifespan` context manager)
                                          │
                                          ▼
                              ws_manager.broadcast(message)
                                          │
                                          ▼
                              All active WebSocket connections
                              for users in the affected organisation
```

The `lifespan` async-context-manager starts the listener task and cancels it
cleanly on shutdown — no orphan tasks, no `@app.on_event` deprecation.

---

## 10. Observability

- **Every request gets a `X-Request-ID`** header (auto-generated if the
  client doesn't supply one). The same ID is bound to every structlog line
  produced by that request.
- **structlog JSON output** is the default — pipe to Loki / CloudWatch / any
  JSON-aware log aggregator without parsing tricks.
- **`X-Process-Time`** response header carries the request duration in
  seconds for ad-hoc curl-based profiling.
- **Health endpoint** at `/health` returns `{ status, service, version }` for
  load balancers.

---

## 11. Security

- bcrypt password hashing.
- JWT HS256, 15-minute access tokens, 7-day refresh tokens; refresh tokens
  hashed at rest and rotated on each refresh.
- TOTP MFA with hashed backup codes; account lockout after 5 failed login
  attempts (15-minute window).
- Redis-backed rate limiting (`60 requests/minute` per IP by default).
- CORS allowlist driven by `ALLOWED_ORIGINS` env var.
- `TrustedHostMiddleware` rejects requests with unexpected `Host` headers in
  production.
- Security headers (`Content-Security-Policy`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, HSTS with
  `preload`, `X-Frame-Options: DENY`, etc.).
- GDPR soft-delete with a 30-day recovery window on users + organisations.
- Immutable `audit_logs` table — append-only at the application layer; 7-year
  retention per the legal-product requirement (NFR-15).

---

## 12. Testing

- `pytest -v` runs **52 / 52** tests in ~35s against an in-memory SQLite DB.
  No external services required.
- Frontend type-checking and bundling: `npm run build` runs `tsc` followed
  by `vite build`. The bundle currently weighs ~552 kB (162 kB gzipped); the
  warning is a known and acceptable trade-off for the demo.
- **CI** (`.github/workflows/ci.yml`) runs three jobs on every PR:
  1. `backend` — pytest against SQLite.
  2. `migrations` — full Postgres 16 service container, `alembic upgrade
     head` → `downgrade -1` → `upgrade head` roundtrip. Catches RLS / trigger
     / partition regressions that SQLite can't see.
  3. `frontend` — `tsc --noEmit` strict + `npm run build`, dist uploaded as
     an artifact.

## 13. Production hardening (the 1.2.0 layer)

These controls are in addition to everything in §11:

- **Body-size limit middleware** rejects oversized JSON bodies before
  Pydantic parses them. `MAX_JSON_BODY_BYTES=1 MB` default; upload routes
  get the larger `MAX_AUDIO_SIZE_BYTES` / `MAX_DOCUMENT_SIZE_BYTES` caps.
- **Stripe-compatible Idempotency-Key middleware** caches mutating-endpoint
  responses in Redis (24 h TTL, keyed by user + method + path + key). Retries
  replay the original outcome with `X-Idempotency-Cached: hit`. Fails-open
  on Redis outage.
- **Row-Level Security** policies on every tenant-scoped table — see
  `SECURITY.md` §6 for permissive vs strict mode.
- **Audit-log partitioning** by month — see migration `0005`. Old months
  can be detached for cheap archival.
- **Exponential backoff + jitter** on every Celery AI task — see
  `app/tasks/*.py` for the `autoretry_for` decorator pattern.
- **Deep `/readiness` probe** for orchestrators that need a real
  "can this instance take traffic" signal.

---

## 13. Data flow summary

```
Browser action
   → React component
   → Zustand store action
   → axios call in services/api.ts (Authorization: Bearer attached automatically)
   → FastAPI route handler
   → Pydantic schema validation (request)
   → SQLAlchemy async query OR Celery enqueue
   → response payload validated through Pydantic (response)
   → TanStack Query caches and propagates to React
   → component re-renders

Long-running:
   → Celery worker reads queue
   → external AI call
   → DB write
   → Redis pub/sub
   → WebSocket fan-out
   → frontend receives event
   → TanStack Query invalidation
   → component re-renders
```
