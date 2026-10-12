-- VeriDictum AI — V001 Initial Schema
-- PostgreSQL 14+ (Flyway-style equivalent of alembic/versions/0001_initial_schema.py)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── ENUM TYPES ───────────────────────────────────────────────────────────────
DO $$ BEGIN CREATE TYPE userrole AS ENUM ('ADMIN','ATTORNEY','PARALEGAL','VIEWER'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE accountstatus AS ENUM ('PENDING_VERIFICATION','ACTIVE','SUSPENDED','LOCKED','DELETED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE subscriptiontier AS ENUM ('FREE','STARTER','PROFESSIONAL','ENTERPRISE'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE casestatus AS ENUM ('ACTIVE','ARCHIVED','CLOSED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE casetype AS ENUM ('CRIMINAL','CIVIL','DEPOSITION','ARBITRATION','HEARING','OTHER'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE casepermission AS ENUM ('VIEWER','EDITOR','CASE_OWNER'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE processingstatus AS ENUM ('PENDING','QUEUED','PROCESSING','COMPLETED','FAILED','RETRYING'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE contradictionseverity AS ENUM ('CRITICAL','HIGH','MEDIUM','LOW','INFO'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE contradictionstatus AS ENUM ('AI_SUGGESTED','CONFIRMED','REJECTED','NEEDS_REVIEW'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE reportstatus AS ENUM ('PENDING','GENERATING','READY','FAILED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ─── ORGANISATIONS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organisations (
    id                UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(255)     NOT NULL,
    slug              VARCHAR(100)     NOT NULL UNIQUE,
    subscription_tier subscriptiontier NOT NULL DEFAULT 'FREE',
    max_users         INTEGER          NOT NULL DEFAULT 5,
    max_cases         INTEGER          NOT NULL DEFAULT 10,
    max_storage_gb    INTEGER          NOT NULL DEFAULT 10,
    is_active         BOOLEAN          NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orgs_slug ON organisations(slug);

-- ─── USERS ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                        UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id           UUID          NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    email                     VARCHAR(254)  NOT NULL,
    full_name                 VARCHAR(255)  NOT NULL,
    phone                     VARCHAR(50),
    password_hash             VARCHAR(255),
    role                      userrole      NOT NULL DEFAULT 'VIEWER',
    account_status            accountstatus NOT NULL DEFAULT 'PENDING_VERIFICATION',
    email_verified            BOOLEAN       NOT NULL DEFAULT FALSE,
    email_verify_token_hash   VARCHAR(255),
    email_verify_expires_at   TIMESTAMPTZ,
    mfa_enabled               BOOLEAN       NOT NULL DEFAULT FALSE,
    mfa_secret                VARCHAR(255),
    backup_codes_hash         TEXT[]        NOT NULL DEFAULT '{}',
    failed_login_attempts     INTEGER       NOT NULL DEFAULT 0,
    locked_until              TIMESTAMPTZ,
    last_login_at             TIMESTAMPTZ,
    last_login_ip             VARCHAR(45),
    password_reset_token_hash VARCHAR(255),
    password_reset_expires_at TIMESTAMPTZ,
    created_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (organisation_id, email)
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_org  ON users(organisation_id);

-- ─── USER SSO LINKS ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_sso_links (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider                VARCHAR(50) NOT NULL,
    provider_user_id        VARCHAR(255) NOT NULL,
    access_token_encrypted  TEXT,
    refresh_token_encrypted TEXT,
    token_expires_at        TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_user_id)
);

-- ─── REFRESH TOKENS ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN     NOT NULL DEFAULT FALSE,
    user_agent  VARCHAR(500),
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_refresh_tokens_hash ON refresh_tokens(token_hash);

-- ─── INVITATIONS ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS invitations (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID        NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    invited_by_id   UUID        REFERENCES users(id) ON DELETE SET NULL,
    email           VARCHAR(254) NOT NULL,
    role            userrole    NOT NULL,
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    accepted_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── CASES ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cases (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID        NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    created_by_id   UUID        REFERENCES users(id) ON DELETE SET NULL,
    case_number     VARCHAR(100) NOT NULL,
    title           VARCHAR(500) NOT NULL,
    court           VARCHAR(255),
    jurisdiction    VARCHAR(255),
    case_type       casetype    NOT NULL DEFAULT 'OTHER',
    status          casestatus  NOT NULL DEFAULT 'ACTIVE',
    description     TEXT,
    tags            TEXT[]      NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at     TIMESTAMPTZ,
    UNIQUE (organisation_id, case_number)
);

CREATE INDEX IF NOT EXISTS ix_cases_org    ON cases(organisation_id);
CREATE INDEX IF NOT EXISTS ix_cases_status ON cases(status);

-- ─── CASE MEMBERS ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS case_members (
    id          UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id     UUID           NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id     UUID           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission  casepermission NOT NULL DEFAULT 'VIEWER',
    added_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    added_by_id UUID           REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (case_id, user_id)
);

-- ─── AUDIO FILES ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audio_files (
    id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id           UUID            NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    uploaded_by_id    UUID            REFERENCES users(id) ON DELETE SET NULL,
    original_filename VARCHAR(500)    NOT NULL,
    blob_name         VARCHAR(1000)   NOT NULL,
    file_size_bytes   BIGINT          NOT NULL,
    duration_seconds  FLOAT,
    mime_type         VARCHAR(100)    NOT NULL,
    sha256_hash       VARCHAR(64)     NOT NULL,
    language_hint     VARCHAR(10),
    speaker_count_hint INTEGER,
    processing_status processingstatus NOT NULL DEFAULT 'PENDING',
    error_message     TEXT,
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audio_case   ON audio_files(case_id);
CREATE INDEX IF NOT EXISTS idx_audio_status ON audio_files(processing_status);

-- ─── TRANSCRIPTS ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transcripts (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    audio_file_id     UUID        NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    case_id           UUID        NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    language_detected VARCHAR(10),
    model_used        VARCHAR(100) NOT NULL DEFAULT 'whisper-large-v3',
    word_count        INTEGER     NOT NULL DEFAULT 0,
    speaker_count     INTEGER     NOT NULL DEFAULT 0,
    processing_time_ms INTEGER,
    full_text         TEXT,
    full_text_tsv     TSVECTOR,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_transcripts_tsv  ON transcripts USING gin(full_text_tsv);
CREATE INDEX IF NOT EXISTS idx_transcripts_case ON transcripts(case_id);

-- ─── TRANSCRIPT SEGMENTS ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transcript_segments (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    transcript_id  UUID        NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    speaker_label  VARCHAR(50) NOT NULL,
    speaker_name   VARCHAR(255),
    start_time     FLOAT       NOT NULL,
    end_time       FLOAT       NOT NULL,
    text           TEXT        NOT NULL,
    confidence     FLOAT,
    is_edited      BOOLEAN     NOT NULL DEFAULT FALSE,
    original_text  TEXT,
    edited_by_id   UUID        REFERENCES users(id) ON DELETE SET NULL,
    edited_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_segments_transcript ON transcript_segments(transcript_id);
CREATE INDEX IF NOT EXISTS idx_segments_speaker   ON transcript_segments(speaker_label);

-- ─── DOCUMENTS ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id           UUID            NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    uploaded_by_id    UUID            REFERENCES users(id) ON DELETE SET NULL,
    original_filename VARCHAR(500)    NOT NULL,
    blob_name         VARCHAR(1000)   NOT NULL,
    file_size_bytes   BIGINT          NOT NULL,
    mime_type         VARCHAR(100)    NOT NULL,
    sha256_hash       VARCHAR(64)     NOT NULL,
    page_count        INTEGER,
    processing_status processingstatus NOT NULL DEFAULT 'PENDING',
    error_message     TEXT,
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_docs_case   ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(processing_status);

-- ─── DOCUMENT PAGES ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS document_pages (
    id               UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number      INTEGER   NOT NULL,
    text             TEXT,
    text_tsv         TSVECTOR,
    confidence       FLOAT,
    bounding_boxes   JSONB,
    is_corrected     BOOLEAN   NOT NULL DEFAULT FALSE,
    corrected_by_id  UUID      REFERENCES users(id) ON DELETE SET NULL,
    corrected_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, page_number)
);

CREATE INDEX IF NOT EXISTS ix_doc_pages_tsv      ON document_pages USING gin(text_tsv);
CREATE INDEX IF NOT EXISTS idx_doc_pages_doc     ON document_pages(document_id);

-- ─── CONTRADICTIONS ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contradictions (
    id                    UUID                   PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id               UUID                   NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    severity              contradictionseverity  NOT NULL,
    status                contradictionstatus    NOT NULL DEFAULT 'AI_SUGGESTED',
    source_a_type         VARCHAR(20)            NOT NULL,
    source_a_id           UUID                   NOT NULL,
    source_a_excerpt      TEXT                   NOT NULL,
    source_a_timestamp    FLOAT,
    source_a_page         INTEGER,
    source_a_speaker      VARCHAR(255),
    source_b_type         VARCHAR(20)            NOT NULL,
    source_b_id           UUID                   NOT NULL,
    source_b_excerpt      TEXT                   NOT NULL,
    source_b_timestamp    FLOAT,
    source_b_page         INTEGER,
    source_b_speaker      VARCHAR(255),
    ai_explanation        TEXT                   NOT NULL,
    ai_confidence         FLOAT                  NOT NULL,
    attorney_note         TEXT,
    reviewed_by_id        UUID                   REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ            NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ            NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_contradictions_case     ON contradictions(case_id);
CREATE INDEX IF NOT EXISTS idx_contradictions_status  ON contradictions(status);
CREATE INDEX IF NOT EXISTS idx_contradictions_severity ON contradictions(severity);

-- ─── ANALYSIS JOBS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID            NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    triggered_by_id     UUID            REFERENCES users(id) ON DELETE SET NULL,
    celery_task_id      VARCHAR(255),
    status              processingstatus NOT NULL DEFAULT 'PENDING',
    contradictions_found INTEGER        NOT NULL DEFAULT 0,
    tokens_used         INTEGER,
    model_used          VARCHAR(100),
    error_message       TEXT,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_case   ON analysis_jobs(case_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);

-- ─── REPORTS ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id          UUID         NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    generated_by_id  UUID         REFERENCES users(id) ON DELETE SET NULL,
    title            VARCHAR(500) NOT NULL,
    status           reportstatus NOT NULL DEFAULT 'PENDING',
    blob_name        VARCHAR(1000),
    sas_url          TEXT,
    sas_expires_at   TIMESTAMPTZ,
    file_size_bytes  BIGINT,
    page_count       INTEGER,
    error_message    TEXT,
    celery_task_id   VARCHAR(255),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reports_case   ON reports(case_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);

-- ─── NL QUERIES ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nl_queries (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id          UUID        NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    asked_by_id      UUID        REFERENCES users(id) ON DELETE SET NULL,
    query_text       TEXT        NOT NULL,
    answer_text      TEXT,
    citations        JSONB       NOT NULL DEFAULT '[]',
    model_used       VARCHAR(100),
    tokens_used      INTEGER,
    response_time_ms INTEGER,
    retrieval_method VARCHAR(50),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_queries_case    ON nl_queries(case_id);
CREATE INDEX IF NOT EXISTS idx_queries_created ON nl_queries(created_at DESC);

-- ─── AUDIT LOGS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID        NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    user_id         UUID        REFERENCES users(id) ON DELETE SET NULL,
    case_id         UUID        REFERENCES cases(id) ON DELETE SET NULL,
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     VARCHAR(255),
    detail          JSONB,
    ip_address      VARCHAR(45),
    user_agent      VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_audit_org     ON audit_logs(organisation_id);
CREATE INDEX IF NOT EXISTS ix_audit_case    ON audit_logs(case_id);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_action  ON audit_logs(action);
