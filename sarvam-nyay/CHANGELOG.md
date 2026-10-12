# Changelog

All notable changes to **VeriDictum AI** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.0] — 2026-05-20

Production-hardening release. Closes the gaps surfaced during the
post-1.1.0 best-practices review: multi-tenant isolation, request-size
limits, deep readiness probing, retry-with-backoff for transient AI
failures, Stripe-style idempotency, CI, pre-commit, and audit-log
partitioning.

### Added — security
- **`SECURITY.md`** — vulnerability disclosure policy, SLA, hardening
  checklist before going live, and the explicit RLS enablement runbook.
- **`CODEOWNERS`** — per-path review routing with dedicated owners for
  database, auth, AI surfaces, and infrastructure.
- **Migration `0004_row_level_security.py`** — Postgres Row-Level Security
  policies on every tenant-scoped table (`users`, `cases`, `case_members`,
  `audio_files`, `transcripts`, `transcript_segments`, `documents`,
  `document_pages`, `contradictions`, `analysis_jobs`, `reports`,
  `nl_queries`, `audit_logs`, `notifications`). Permissive-by-default so
  the existing app-level `WHERE organisation_id = …` queries keep working;
  `FORCE` runbook documented in `SECURITY.md` §6 for strict production
  mode.
- **Body-size limit middleware** — rejects requests exceeding
  `MAX_JSON_BODY_BYTES` (default 1 MB) before Pydantic touches them.
  Upload routes (`/audio`, `/documents`) get the larger
  `MAX_AUDIO_SIZE_BYTES` / `MAX_DOCUMENT_SIZE_BYTES` caps.

### Added — reliability
- **Deep `/readiness` endpoint** — probes PostgreSQL (`SELECT 1`) and Redis
  (`PING`), returns per-subsystem `status` + `duration_ms`. Returns 503
  with structured diagnostics when any required dependency is unreachable.
  `/health` stays cheap for load-balancer liveness.
- **Exponential backoff + jitter on every Celery AI task** —
  `autoretry_for=(ConnectionError, TimeoutError, OSError)` with
  `retry_backoff=True` and `retry_jitter=True` on transcription, OCR,
  analysis, and report tasks. Replaces manual `self.retry(countdown=…)`
  loops with Celery's first-class backoff so transient OpenAI / Azure DI
  / DeepInfra failures don't surface to the user.
- **Stripe-compatible Idempotency-Key middleware** — when a mutating
  request carries an `Idempotency-Key` header, the response is cached in
  Redis with a 24-hour TTL keyed by user + method + path + key. A retry
  with the same key replays the original outcome verbatim with
  `X-Idempotency-Cached: hit` and `Idempotency-Replayed: true`. In-flight
  lock prevents simultaneous retries from both running. Fails-open if
  Redis is unreachable so attorneys can still create reports during a
  cache outage.

### Added — ops & developer experience
- **`.github/workflows/ci.yml`** — three CI jobs:
  - `backend`: SQLite pytest run on every PR.
  - `migrations`: full Postgres 16 service container with `alembic
    upgrade head` + `downgrade -1` + `upgrade head` roundtrip — catches
    RLS / trigger / partition regressions that SQLite can't see.
  - `frontend`: `tsc --noEmit` strict + `npm run build`, dist uploaded as
    a build artifact.
  - PR-only: `dependency-review` action with `fail-on-severity: high`.
- **`.github/PULL_REQUEST_TEMPLATE.md`** — enforces the
  `CONTRIBUTING.md` PR checklist at PR-creation time.
- **`.github/dependabot.yml`** — weekly dependency PRs for pip, npm, and
  Actions; minor + patch updates are grouped.
- **`.pre-commit-config.yaml`** — ruff (lint + format) + black-via-ruff +
  prettier + `tsc --noEmit` + detect-secrets + standard hygiene hooks.
- **`backend/pyproject.toml`** — ruff configuration (target Py 3.12, 100
  cols, B/C4/UP/ASYNC/S/RUF rule set) and `pytest` config inline.

### Added — database / performance
- **Migration `0005_partitioning_extensions.py`**:
  - **`pg_trgm` extension** + GIN trigram index on `cases.title` for
    typo-tolerant fuzzy search.
  - **`citext` extension** + `users.email` converted to `citext` so
    `Sarah@firm.com` and `sarah@firm.com` are correctly recognised as the
    same user. Composite uniqueness constraint
    `uq_user_org_email(organisation_id, email)` recreated with
    case-insensitive semantics.
  - **`audit_logs` partitioned by month** on `created_at`. 24 months
    backward + 12 forward materialised at migration time; default
    partition catches anything outside the window. PK changed to
    `(id, created_at)` per Postgres partitioning rules; indexes
    (`ix_audit_org`, `ix_audit_case`, `ix_audit_created`) recreated on
    the parent so new partitions inherit them automatically. Sanity
    block guards the legacy → partitioned row-count migration.
  - Full `downgrade()` path that reverts each change cleanly.

### Changed
- **`/health` body** — version string updated to 1.1.0 baseline; structure
  unchanged so existing load-balancer probes continue working.
- **`CHANGELOG.md`** entry for this release.
- **`README.md`**, **`ARCHITECTURE.md`**, **`DEPLOYMENT.md`**,
  **`CONTRIBUTING.md`** — refreshed to reference the new endpoints,
  middleware, migrations, and CI/pre-commit workflows.

### Verified
- `pytest`: **52 / 52 passing** in ~35 s.
- `npm run build`: TypeScript strict-mode clean, Vite bundle 552 kB
  (162 kB gzipped).
- Live smoke against the running stack:
  - `/health` returns the cheap liveness body.
  - `/readiness` reports DB ok (92 ms) and Redis ok (317 ms).
  - Body-size cap returns **HTTP 413** for oversized JSON; **HTTP 401**
    (auth, not middleware) on small JSON without auth.
  - `Idempotency-Key` >255 chars → **HTTP 400**.
  - First valid `Idempotency-Key` call → 201 Created + cache miss.
  - Replayed call → 201 Created + cache hit, `Idempotency-Replayed: true`,
    no duplicate row created.

---

## [1.1.0] — 2026-05-20

This release closes every show-stopper surfaced by the marketing-grade
screenshot audit and tightens the database, backend, and frontend along the
way. See `project-audit/SCREENSHOT_MARKETING_AUDIT.md` for the audit and
`project-audit/AUDIT_FIXES_APPLIED.md` for the per-fix log.

### Added
- **`seed_screenshots.py`** — new marketing-grade demo seeder. Creates 15
  topically-coherent cases, each with **unique** audio filenames; seeds three
  real contradictions on the lead case (`People v. Marcus Whitfield`); seeds
  a mix of COMPLETE / GENERATING / QUEUED reports so the Reports page tells
  a workflow story; seeds NLQuery history with citations.
- **Alembic migration `0003_perf_triggers_fts.py`** — PostgreSQL trigger
  `set_updated_at` attached to every table with an `updated_at` column; GIN
  tsvector indexes on `transcripts.full_text` and `documents.extracted_text`
  (the 3-pass RAG engine's "Pass 2" is now backed by a real GIN index);
  composite indexes on hot query paths (`cases (org_id, status)`,
  `contradictions (case_id, severity)`, `contradictions (case_id, status)`,
  `reports (case_id, status)`, `audio_files (case_id, status)`,
  `documents (case_id, status)`, `notifications (user_id, is_read, created_at DESC)`);
  CHECK constraints on `confidence_score ∈ [0,1]`, `avg_confidence ∈ [0,1]`,
  `document_page > 0`, `file_size_bytes >= 0`. The migration is PostgreSQL-only
  and silently no-ops on SQLite (used by the test suite).
- **Global `ErrorBoundary`** wraps the entire React app. Catches render-time
  errors and shows a recovery surface instead of a white screen, with a stack
  trace in dev mode.
- **Stronger security headers** — `Content-Security-Policy` (production),
  `Permissions-Policy` denying every browser-feature surface we don't use,
  `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy:
  same-site`, HSTS upgraded to `preload`.
- **New per-case stats fields** — `GET /api/v1/cases/{id}/contradictions/summary/stats`
  now returns `pending_review` and `avg_confidence` so the case header and
  AI Case Summary tile no longer hard-code these as "0" and "N/A".
- **Dashboard severity stack** — Contradictions stat card now shows a
  per-severity breakdown (`2 critical · 3 high · 1 medium`) under the
  headline number, hiding zero-count buckets.
- **Empty-state preview thumbnail** on the Contradictions tab — a faded mock
  of a populated card answers the prospect's "what will I see once I run
  analysis?" question without requiring them to click Run Analysis first.
- **Active-state accent rail** in the sidebar — every active nav item now
  carries a gold left-edge rail + shadow so the active state is visually
  unmistakable next to hover.
- **CTA hierarchy** on the case header — one filled primary (`Run Analysis`),
  one outline secondary (`Generate Report`); tertiary actions
  (`Run Courtroom Audit`, `Download Courtroom Brief`) collapsed into a
  `… More` ghost-button dropdown.
- **Documentation rewrite** — `README.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`,
  `QUICKSTART.md`, `CONTRIBUTING.md`, and this CHANGELOG fully refreshed to
  reflect the current codebase.

### Changed
- **FastAPI lifespan** — replaced deprecated `@app.on_event("startup")` /
  `@app.on_event("shutdown")` with the modern `lifespan` async context
  manager. No behaviour change; ends the deprecation warning and makes the
  pub/sub task cancellation deterministic.
- **`Layout.tsx` nav-active logic** — replaced `pathname.startsWith(item.href)`
  (which collided on `/cases/{id}/reports` matching both Cases and Reports)
  with a precise `isNavActive` helper.
- **Citation chip rendering** in `NLQueryPage.tsx` — chips fall back gracefully
  when `page` or `timestamp` is null (no more bare `Doc p.`). Audio chips show
  `Speaker · MM:SS`; document chips show `Doc · p. N`.
- **AI Case Summary** now reflects real evidence counts (audio + document
  queries are now eager so the summary tile always has accurate counts
  regardless of which tab is active). Pluralisation fix: "1 critical
  discrepancy requires" (not "require").
- **Cases-list status pill** gained an inset ring + coloured status dot.
- **Topbar identity** — `Sarah Blackwood · Admin` collapsed into
  `Sarah Blackwood [Admin]` with a navy chip-style role badge.
- **`backend/.env.example`** — `DATABASE_URL` now defaults to
  `sqlite+aiosqlite:///./veridictum.db` (async driver), fixing the previous
  default that crashed `create_async_engine` with "pysqlite is not async".

### Fixed
- **S-1 (CRITICAL)** — Contradictions tab on every case showed
  "No contradictions detected yet" while the header badge said `CRITICAL 1`.
  Root cause: the previous demo driver tried to direct-insert contradictions
  but failed on the `transcripts.audio_file_id NOT NULL` constraint and
  silently left the table empty. The new `seed_screenshots.py` inserts three
  real, FK-coherent contradictions on the lead case.
- **S-2 (CRITICAL)** — three demo cases shared the same audio filenames
  (`TrialDay2.wav`, `WitnessDeposition.wav`, `ExpertOpinion.wav`). Each case
  now has topically-unique audio.
- **S-3 (CRITICAL)** — adjacent screenshots showed different users
  (`Demo Admin` vs `Sarah Blackwood`). The seeder now locks the persona
  name on every re-seed.
- **S-4 (HIGH)** — Settings page rendered two simultaneously-active sidebar
  items (`Reports` carrying hover-bleed at the same time as `Settings`
  carrying the chevron). Replaced fragile `startsWith` with `isNavActive` and
  raised the active-state visual weight to make hover and active impossible
  to confuse.
- **S-5 (HIGH)** — `AI Case Summary` reported `0 audio files · 0 documents`
  on first load because those queries were `enabled: activeTab === "audio"`.
  Made them eager (`enabled: !!caseId`).
- **S-6 (HIGH)** — citation chips rendered `Doc p.` with no number when the
  page index was null. Chips now build labels safely with explicit fallbacks.
- **AI Case Summary `Confidence: N/A`** — the per-case stats endpoint never
  returned `avg_confidence`. Added it and threaded it through the UI.

### Security
- Stronger CSP, COOP, CORP, and `Permissions-Policy` in production responses.
- HSTS `preload` token added for HTTPS-only enforcement.
- All previous controls (bcrypt, refresh-token rotation, account lockout,
  TOTP MFA, Redis rate limiting, refresh-token revocation on logout, GDPR
  soft-delete, security headers) retained.

### Testing
- `pytest`: **52 / 52 passed** (~22s, SQLite in-memory, no external services).
- `npm run build`: TypeScript compiles, Vite bundles, **zero errors**.
- Full stack smoke-tested with the seeded data:
  - Login → dashboard renders 15 cases / 6 contradictions / 16 documents / 21 audio.
  - Whitfield case → Contradictions tab shows 3 real cards (1 CRITICAL + 2 HIGH).
  - Ask AI history shows two seeded Q&A pairs with proper `Doc · p. N` and
    `Marcus Whitfield · 2:14` citation chips.

---

## [1.0.0] — 2026-05-17

### Added
- Initial release.
- Courtroom audio upload with DeepInfra Whisper Large v3 transcription and
  speaker diarization.
- Legal document OCR via Azure Document Intelligence (PDF, DOCX).
- AI-powered factual contradiction detection using OpenAI GPT-4.1-nano with
  structured-output JSON mode.
- Contradiction severity classification: CRITICAL, HIGH, MEDIUM, LOW,
  INFORMATIONAL.
- Natural-language RAG query interface with 3-pass retrieval
  (Pinecone vectors + PostgreSQL FTS + keyword LIKE + full-corpus fallback).
- Attorney review workflow: `AI_SUGGESTED` → `CONFIRMED` / `REJECTED`.
- PDF report generation (ReportLab) with contradiction cards and severity
  badges; uploaded to Azure Blob and served via 24-hour SAS URLs.
- JWT HS256 authentication with 15-minute access tokens and 7-day refresh
  tokens.
- TOTP MFA with account lockout (5 failed attempts / 15 min).
- WebSocket real-time notifications for async task completion.
- Celery task queues: transcription, OCR, analysis, reports.
- Case management with multi-member access control (Viewer / Editor /
  Case Owner) and immutable audit log.
- In-app notification system.
- React 18 + Vite 5 + TypeScript SPA with Tailwind CSS dark navy / gold
  theme.
- Zustand state management with localStorage persistence.
- Full Swagger UI and ReDoc API documentation.
- Docker Compose with 8 services including Celery Flower monitoring.

### Security
- bcrypt password hashing.
- TOTP MFA with backup-code recovery.
- CORS origin whitelisting.
- Rate limiting middleware (Redis-backed).
- Account lockout after 5 failed login attempts.
- GDPR soft-delete with 30-day recovery window.
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, HSTS,
  `Referrer-Policy`, `X-XSS-Protection`.

---

*AI-generated contradiction analysis and query answers must be verified by a
licensed attorney before any legal use. VeriDictum AI is a decision-support
tool, not a substitute for professional legal judgement.*
