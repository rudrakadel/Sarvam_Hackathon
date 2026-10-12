# Deployment Guide — VeriDictum AI

> Production deployment of the full VeriDictum stack: FastAPI API,
> 4 Celery worker pools, PostgreSQL 16, Redis 7, Flower, plus the React SPA.

For local development, see [`QUICKSTART.md`](QUICKSTART.md). For the system
design that this guide deploys, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Deployment options

| Mode               | When to use                                | Section |
| ------------------ | ------------------------------------------ | ------- |
| Docker Compose     | Single-host VPS, demos, staging            | §2      |
| Kubernetes         | Production at scale, multiple environments | §3      |
| Bare-metal / VM    | Air-gapped or enterprise-restricted        | §4      |

Whichever path you pick, the bring-up sequence is the same:

1. Provision secrets (env vars).
2. Build / pull images.
3. Run database migrations: `alembic upgrade head`.
4. Optionally seed demo data: `python seed_screenshots.py --fresh`.
5. Start API, workers, and frontend.

---

## 2. Docker Compose (single-host)

### 2.1 Prerequisites

- Docker 24+
- Docker Compose v2

### 2.2 Configure env

```bash
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum:
#   SECRET_KEY=<64 hex chars from `python -c "import secrets; print(secrets.token_hex(32))"`>
#   DATABASE_URL=postgresql+asyncpg://veridictum:<pwd>@postgresql:5432/veridictum
#   SYNC_DATABASE_URL=postgresql+psycopg2://veridictum:<pwd>@postgresql:5432/veridictum
#   ALLOWED_ORIGINS=https://app.veridictum.example.com
#   OPENAI_API_KEY=sk-...
#   DEEPINFRA_API_KEY=...
#   AZURE_DOC_INTELLIGENCE_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
#   AZURE_DOC_INTELLIGENCE_KEY=...
#   AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=...
#   PINECONE_API_KEY=...  (optional — RAG falls back to PostgreSQL FTS)
```

### 2.3 Build and start

```bash
cd backend
docker compose up --build -d
```

Services brought up:

| Container                          | Role                            | Port |
| ---------------------------------- | ------------------------------- | ---- |
| `veridictum_api`                   | FastAPI (4 Uvicorn workers)     | 8000 |
| `postgresql`                       | PostgreSQL 16                   | 5432 |
| `veridictum_redis`                 | Redis 7                         | 6379 |
| `veridictum_celery_transcription`  | Whisper worker pool (2)         | —    |
| `veridictum_celery_ocr`            | Azure DI OCR worker pool (4)    | —    |
| `veridictum_celery_analysis`       | GPT analysis worker pool (2)    | —    |
| `veridictum_celery_reports`        | ReportLab PDF worker pool (2)   | —    |
| `veridictum_flower`                | Celery monitoring UI            | 5555 |

### 2.4 Migrate the database

```bash
docker compose exec api alembic upgrade head
```

This runs all five migrations:

- `0001_initial_schema` — every table, enum, foreign key, unique constraint.
- `0002_add_notifications` — notifications table + indexes.
- `0003_perf_triggers_fts` — **PostgreSQL-only**: `updated_at` triggers, GIN
  tsvector indexes, composite indexes on hot paths, CHECK constraints.
- `0004_row_level_security` — **PostgreSQL-only**: RLS policies on every
  tenant-scoped table. Permissive-by-default; enable strict mode with the
  block in `SECURITY.md` §6 after creating your production app role.
- `0005_partitioning_extensions` — **PostgreSQL-only**: enables `pg_trgm`
  (typo-tolerant fuzzy search on case titles) + `citext` (case-insensitive
  email uniqueness); converts `audit_logs` to a month-range partitioned
  table (24 months back + 12 forward materialised at migration time, plus
  a default catch-all partition). Old partitions can be detached for cheap
  archival to meet the 7-year retention contract without bloating the
  hot path.

### 2.5 (Optional) Seed demo data

```bash
docker compose exec api python seed_screenshots.py --fresh
```

Logs the persona credentials:

```
persona : Sarah Blackwood (admin@blackwoodlaw.com / Demo@Pass123!)
```

### 2.6 Frontend build

The frontend ships as a static bundle. Build it once, serve with any
static file server (nginx, Caddy, S3 + CloudFront):

```bash
cd frontend
npm install
echo "VITE_API_URL=https://api.veridictum.example.com/api/v1" > .env.production
echo "VITE_WS_URL=wss://api.veridictum.example.com" >> .env.production
npm run build
# Deploy ./dist/ to your static host of choice
```

---

## 3. Kubernetes

A reference Helm chart is not in-repo today, but the workload shape is:

| Workload                  | Replicas | CPU req | Mem req | Notes                                              |
| ------------------------- | -------- | ------- | ------- | -------------------------------------------------- |
| `api` (FastAPI/Uvicorn)   | 2–4      | 500m    | 1Gi     | Stateless. Liveness probe → `/health`.              |
| `worker-transcription`    | 1–2      | 1       | 2Gi     | I/O bound on DeepInfra; tolerate restart.           |
| `worker-ocr`              | 2–4      | 500m    | 1Gi     | Azure DI is rate-limited; scale with budget.        |
| `worker-analysis`         | 1–2      | 500m    | 1Gi     | OpenAI rate-limited.                                |
| `worker-reports`          | 1        | 250m    | 512Mi   | Bursty; ReportLab is CPU heavy.                     |
| `frontend` (nginx)        | 2        | 100m    | 128Mi   | Serves static `dist/`. No state.                    |
| `postgresql`              | StatefulSet | 1    | 4Gi     | Managed RDS / Cloud SQL preferred in production.    |
| `redis`                   | 1        | 250m    | 512Mi   | Persist enabled. Managed Elasticache preferred.     |

Recommendations:

- **Run migrations via a Kubernetes `Job`** that completes before the API
  Deployment rolls. `helm-charts/api/templates/migration-job.yaml` would
  invoke `alembic upgrade head` on every release.
- **Secrets** live in the cluster secret store (External Secrets Operator
  bound to Azure Key Vault / AWS Secrets Manager / GCP Secret Manager). Do
  not bake secrets into images.
- **HPA** on `api` and the worker pools based on CPU + queue depth.
- **Ingress with TLS termination**. The CSP header in production assumes
  HTTPS-only.

---

## 4. Bare-metal / VM

### 4.1 Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env (see §2.2)

# Migrate
alembic upgrade head

# Run with Gunicorn + Uvicorn workers, behind nginx
gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile -
```

### 4.2 Celery workers (one process per queue)

```bash
celery -A app.tasks.celery_app worker -Q transcription -c 2 -n transcription@%h
celery -A app.tasks.celery_app worker -Q ocr           -c 4 -n ocr@%h
celery -A app.tasks.celery_app worker -Q analysis      -c 2 -n analysis@%h
celery -A app.tasks.celery_app worker -Q reports       -c 2 -n reports@%h
```

Run each under a process manager (`systemd`, `supervisord`).

Example `systemd` unit (`/etc/systemd/system/veridictum-worker-analysis.service`):

```ini
[Unit]
Description=VeriDictum Celery worker — analysis queue
After=network.target

[Service]
Type=simple
User=veridictum
WorkingDirectory=/opt/veridictum/backend
EnvironmentFile=/opt/veridictum/backend/.env
ExecStart=/opt/veridictum/backend/.venv/bin/celery -A app.tasks.celery_app \
    worker -Q analysis -c 2 -n analysis@%H
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4.3 Frontend (nginx)

```bash
cd frontend
npm install
echo "VITE_API_URL=https://api.veridictum.example.com/api/v1" > .env.production
echo "VITE_WS_URL=wss://api.veridictum.example.com" >> .env.production
npm run build
```

nginx site (`/etc/nginx/sites-available/veridictum.conf`):

```nginx
server {
    listen 443 ssl http2;
    server_name app.veridictum.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.veridictum.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.veridictum.example.com/privkey.pem;

    root /var/www/veridictum;
    index index.html;

    # SPA — every unknown route falls through to index.html
    location / {
        try_files $uri /index.html;
    }

    # Long cache for fingerprinted assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

The API is best fronted by a separate nginx vhost or an L7 load balancer at
`https://api.veridictum.example.com`.

---

## 5. Environment variables reference

The single source of truth is `backend/.env.example`. Required variables for
production deployment:

| Variable                            | Required | Description                                                |
| ----------------------------------- | -------- | ---------------------------------------------------------- |
| `SECRET_KEY`                        | **YES**  | JWT signing key — 64+ random hex chars. Never reuse.       |
| `DATABASE_URL`                      | **YES**  | `postgresql+asyncpg://user:pass@host:5432/veridictum`      |
| `SYNC_DATABASE_URL`                 | **YES**  | `postgresql+psycopg2://...` — used by Alembic              |
| `ALLOWED_ORIGINS`                   | **YES**  | Comma-separated CORS allowlist                              |
| `REDIS_URL`                         | **YES**  | `redis://redis:6379/0`                                     |
| `CELERY_BROKER_URL`                 | **YES**  | `redis://redis:6379/1`                                     |
| `CELERY_RESULT_BACKEND`             | **YES**  | `redis://redis:6379/2`                                     |
| `OPENAI_API_KEY`                    | **YES**  | Contradiction detection + RAG synthesis                    |
| `OPENAI_MODEL`                      | No       | Default `gpt-4.1-nano-2025-04-14`                          |
| `DEEPINFRA_API_KEY`                 | **YES**  | Whisper Large v3 transcription                             |
| `WHISPER_MODEL`                     | No       | Default `openai/whisper-large-v3`                          |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT`   | **YES**  | Azure DI endpoint URL                                       |
| `AZURE_DOC_INTELLIGENCE_KEY`        | **YES**  | Azure DI API key                                            |
| `AZURE_STORAGE_CONNECTION_STRING`   | **YES**  | Azure Blob — audio + documents + signed PDF reports         |
| `PINECONE_API_KEY`                  | No       | Pinecone vector search. Omit to use PG FTS fallback only.   |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`   | No       | Default 15                                                  |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS`     | No       | Default 7                                                   |
| `RATE_LIMIT_PER_MINUTE`             | No       | Default 60                                                  |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | No | Outbound email (password reset, invitations)         |

---

## 6. Database operations

### Backup

```bash
# Inside the postgres container:
docker compose exec postgresql pg_dump -U veridictum -d veridictum -Fc \
    > veridictum-$(date +%Y%m%d).pgdump
```

### Restore

```bash
docker compose exec -T postgresql pg_restore -U veridictum -d veridictum \
    --clean --if-exists < veridictum-20260520.pgdump
```

### Migration commands

```bash
alembic current                         # show current revision
alembic history                         # show all revisions
alembic upgrade head                    # apply all pending migrations
alembic downgrade -1                    # revert one revision
alembic revision --autogenerate -m "X"  # generate new revision from model diff
```

Always review autogenerated migrations before committing — Alembic doesn't
detect server-side defaults, CHECK constraints, or trigger changes.

---

## 7. Observability

- **Logs:** structlog JSON on stdout. Pipe to your aggregator.
- **Tracing:** every response carries `X-Request-ID`; every log line is
  bound to that ID.
- **Metrics:** Flower exposes Celery task metrics at `:5555`. For HTTP-level
  metrics, terminate behind an L7 proxy that exports Prometheus.
- **Alerting hooks** (suggested, not in-repo):
  - High `5xx` rate on `/api/v1/...`.
  - Celery queue depth > 100 for >5 min on the `analysis` or
    `transcription` queues.
  - PostgreSQL connection pool saturation.

---

## 7a. Audit log partition rotation (Day-2 ops)

Migration `0005` materialises 24 months back + 12 forward of monthly
`audit_logs` partitions, plus an `audit_logs_default` catch-all. As time
moves on you must:

- **Add forward partitions** monthly (or weekly via a cron job). Example
  for next March:
  ```sql
  CREATE TABLE audit_logs_y2026m03
  PARTITION OF audit_logs
  FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
  ```
- **Detach old partitions** (anything past your retention SLA) and move
  them to cold storage:
  ```sql
  ALTER TABLE audit_logs DETACH PARTITION audit_logs_y2019m01 CONCURRENTLY;
  -- pg_dump audit_logs_y2019m01 → S3 / archival blob
  DROP TABLE audit_logs_y2019m01;
  ```
- **Monitor `audit_logs_default`.** Any row landing there is a sign you
  missed a forward partition. Set up an alert:
  `SELECT count(*) FROM audit_logs_default;` should be 0.

A recommended ops cron (illustrative — wire into your scheduler of choice):

```sql
-- Create next month's partition if it doesn't exist
DO $$
DECLARE next_month date := date_trunc('month', now() + interval '2 months')::date;
DECLARE part_name text := format('audit_logs_y%sm%s',
    to_char(next_month, 'YYYY'),
    to_char(next_month, 'MM')
);
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF audit_logs FOR VALUES FROM (%L) TO (%L)',
        part_name,
        next_month,
        next_month + interval '1 month'
    );
END $$;
```

## 8. Security checklist (before going live)

- [ ] `SECRET_KEY` is freshly generated and 64+ hex chars.
- [ ] `ALLOWED_ORIGINS` lists only your real domain(s) — no `*`, no
      `localhost`.
- [ ] `.env` is **never** committed; secrets live in Key Vault / Secrets
      Manager.
- [ ] HTTPS terminates at the edge; HSTS is on (the production `CSP` builder
      assumes HTTPS).
- [ ] API keys (OpenAI, DeepInfra, Azure DI, Azure Storage, Pinecone) are
      rotated from their dev/staging values.
- [ ] WebSocket `/ws/...` endpoints have JWT auth enabled.
- [ ] PostgreSQL `superuser` is not the app user; the app role has only
      `CREATE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE` on its schema.
- [ ] Alembic migrations have been applied (`alembic current` = `0003`).
- [ ] Demo seed data is **not** in your production DB.
- [ ] Backup job is scheduled and a restore has been tested.
- [ ] Rate-limit budget (`RATE_LIMIT_PER_MINUTE`) matches your traffic
      profile.
- [ ] `MAX_JSON_BODY_BYTES` is sized for your largest legitimate
      non-upload request.
- [ ] Migration `0004` ran AND you've executed the `FORCE ROW LEVEL
      SECURITY` block from `SECURITY.md` §6 (strict mode).
- [ ] Audit-log partition rotation cron is scheduled (see §7a).
- [ ] `/readiness` is wired up as the orchestrator's readiness probe (NOT
      `/health` — that's liveness only).

---

## 9. Upgrading

Between minor versions:

```bash
git pull
docker compose pull               # if you use registry images
docker compose build              # if you build locally
docker compose up -d
docker compose exec api alembic upgrade head
```

Always read `CHANGELOG.md` first — schema-changing releases (anything that
adds an Alembic revision) require running `alembic upgrade head` after the
new container is up.
