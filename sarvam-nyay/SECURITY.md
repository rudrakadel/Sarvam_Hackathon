# Security Policy — VeriDictum AI

VeriDictum AI processes courtroom evidence, expert testimony, and document
discovery — sensitive content under attorney-client privilege. Security is a
first-class concern, not an afterthought.

This document describes:

1. [Supported versions](#1-supported-versions)
2. [Reporting a vulnerability](#2-reporting-a-vulnerability)
3. [What we promise](#3-what-we-promise)
4. [Out-of-scope](#4-out-of-scope)
5. [In-tree controls](#5-in-tree-controls)
6. [Multi-tenant isolation (RLS)](#6-multi-tenant-isolation-rls)
7. [Hardening checklist before production](#7-hardening-checklist-before-production)

---

## 1. Supported versions

| Version | Security fixes |
| ------- | -------------- |
| `1.1.x` | ✅ Yes          |
| `1.0.x` | ⚠️ Critical only |
| `< 1.0` | ❌ Unsupported  |

---

## 2. Reporting a vulnerability

**Do not open a public GitHub issue for security reports.**

Email security@veridictum.ai (or the address your deploying organisation
publishes) with:

- A clear description of the vulnerability and its impact.
- Step-by-step reproduction instructions.
- The version / commit SHA you tested against.
- Any proof-of-concept code (treat sensitive payloads responsibly).
- Your preferred attribution name (or "anonymous").

You should receive an acknowledgement within **2 business days**, an initial
triage verdict within **5 business days**, and a patch ETA within **10
business days** for confirmed High/Critical issues.

We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure):
please give us **90 days** to issue a fix before public disclosure. We will
credit you in the release notes if you wish.

---

## 3. What we promise

| Severity                | Acknowledge | Patch ETA           |
| ----------------------- | ----------- | ------------------- |
| **Critical** (RCE, auth bypass, tenant leak, data exfil) | 2 business days | 7 calendar days |
| **High** (privilege escalation, persistent XSS, sensitive log leak)  | 2 business days | 21 calendar days |
| **Medium** (input validation, lower-impact info disclosure) | 5 business days | 60 calendar days |
| **Low** (rate-limit gaps, ergonomic hardening) | 5 business days | next minor release |

After the patch is released, we publish a public advisory with:

- A description of the issue.
- Affected versions.
- The fix (commit SHA + PR link).
- Credit to the reporter (with consent).

---

## 4. Out-of-scope

The following do not qualify as security vulnerabilities under this policy:

- Findings that require a malicious admin or an already-compromised
  credential.
- Denial of service via high traffic against a single instance (use a CDN /
  WAF / rate limiter at the edge — that's a deployment concern).
- Lack of HSTS, CSP, or rate limits on instances explicitly configured for
  `DEBUG=true` (development mode).
- Self-XSS that requires the user to paste hostile content into their own
  browser.
- "Best practice" findings without a concrete impact path (e.g. "you don't
  set X-Permitted-Cross-Domain-Policies").
- Third-party dependency CVEs that are not exploitable in our integration —
  please file these as regular issues so Dependabot tracks them.

---

## 5. In-tree controls

The repository ships with these controls. Most are documented further in
[`ARCHITECTURE.md`](ARCHITECTURE.md) §11.

### Authentication & authorization
- bcrypt password hashing (cost factor 12).
- JWT HS256 with 15-minute access tokens and 7-day refresh tokens.
- Refresh tokens are hashed at rest and rotated on every refresh.
- TOTP MFA with hashed backup codes; lockout after 5 failed attempts in 15 min.
- Per-case permission tiers: `VIEWER` < `EDITOR` < `CASE_OWNER`.
- WebSocket endpoints accept the same JWT bearer.

### Transport & headers
- CORS allowlist driven by `ALLOWED_ORIGINS`.
- TrustedHost middleware rejects unexpected `Host` headers in production.
- Production responses carry: `Content-Security-Policy`, `Permissions-Policy`
  (denies camera / microphone / geolocation / payment / USB / etc.),
  `Cross-Origin-Opener-Policy: same-origin`,
  `Cross-Origin-Resource-Policy: same-site`,
  `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`,
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`.

### Rate limiting & DoS
- Redis-backed per-IP rate limit (default 60 req/min).
- **Body-size limit middleware**: rejects oversized JSON before Pydantic
  parses it (`MAX_JSON_BODY_BYTES`, default 1 MB). Upload routes get a
  larger cap (`MAX_AUDIO_SIZE_BYTES`, `MAX_DOCUMENT_SIZE_BYTES`).
- **Idempotency-Key header support** prevents duplicate side-effects from
  retried POSTs.

### Database
- UUID primary keys with `gen_random_uuid()` server default — no enumerable
  IDs in URLs.
- Cascade rules tuned per relationship (audit logs survive user deletion via
  `ON DELETE SET NULL`; tenant data cascades on org deletion).
- `set_updated_at()` Postgres trigger (migration `0003`) — `updated_at` stays
  authoritative even for direct SQL updates.
- CHECK constraints (migration `0003`): confidence in [0, 1], page numbers
  positive, file sizes non-negative.
- **Row-Level Security policies** (migration `0004`) — see §6.

### Audit trail
- Every meaningful attorney action writes an `audit_logs` row with the
  user ID, timestamp, IP, user-agent, and a structured `detail` JSON.
- `audit_logs` is append-only at the application layer; a `7-year` retention
  contract is documented and partitioning (migration `0005`) keeps queries
  fast.

### Privacy
- GDPR soft-delete on users and organisations with a 30-day recovery
  window.
- Sensitive fields are excluded from API responses by Pydantic
  `response_model_exclude` rules.

---

## 6. Multi-tenant isolation (RLS)

Migration `0004_row_level_security.py` enables **Postgres Row-Level
Security** on every tenant-scoped table:

```
users · cases · case_members · audio_files · transcripts ·
transcript_segments · documents · document_pages ·
contradictions · analysis_jobs · reports · nl_queries ·
audit_logs · notifications
```

Each table has a policy that compares `organisation_id` (directly or via a
join) against `current_setting('app.current_org_id')::uuid`. The app sets
this GUC at the start of each authenticated request.

### Enforcement modes

| Mode                | When to use                                       | How                                                    |
| ------------------- | ------------------------------------------------- | ------------------------------------------------------ |
| **Permissive (default)** | Migrations, admin scripts, the test suite     | Policies exist but RLS is `ENABLE`d, not `FORCE`d. The app user is the table owner, so it bypasses unless `FORCE` is on. The existing app-level `WHERE organisation_id = …` filters remain the primary guard. |
| **Strict (recommended for production)** | Production deployments                  | Run `ALTER TABLE <each_table> FORCE ROW LEVEL SECURITY;` once after the app user is created. Now ANY query missing the GUC returns zero rows — defence-in-depth catches a forgotten WHERE. |

To enable strict mode in production (one-time):

```sql
DO $$ DECLARE t text;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'users','cases','case_members','audio_files','transcripts',
        'transcript_segments','documents','document_pages',
        'contradictions','analysis_jobs','reports','nl_queries',
        'audit_logs','notifications'
    ]) LOOP
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
    END LOOP;
END $$;
```

To revert:

```sql
DO $$ DECLARE t text;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'users','cases','case_members','audio_files','transcripts',
        'transcript_segments','documents','document_pages',
        'contradictions','analysis_jobs','reports','nl_queries',
        'audit_logs','notifications'
    ]) LOOP
        EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY;', t);
    END LOOP;
END $$;
```

### Setting the tenant context per request

For strict mode, the app must run on every connection checkout:

```sql
SET LOCAL app.current_org_id = '<resolved-org-uuid>';
```

This is wired into `app/api/deps.py:get_tenant_db` (added in version 1.2.0
as a follow-up to migration `0004`). Routes that need RLS use
`Depends(get_tenant_db)` instead of `Depends(get_db)`. SQLite test paths
short-circuit the SET because RLS is a Postgres feature.

---

## 7. Hardening checklist before production

This is the literal checklist your release engineer should walk before flipping DNS:

- [ ] `SECRET_KEY` is freshly generated, 64+ hex chars, and **not** the dev value.
- [ ] `ALLOWED_ORIGINS` is your production domain(s) only — no `*`, no
      `localhost`, no `*.staging.*`.
- [ ] `DEBUG=false` in production. (Docs UIs at `/docs` and `/redoc` are
      automatically disabled when `DEBUG=false`.)
- [ ] HTTPS terminates at the edge; HSTS is on (the CSP builder assumes
      HTTPS-only).
- [ ] All AI API keys (OpenAI, DeepInfra, Azure DI, Azure Storage, Pinecone)
      are freshly rotated from dev/staging values.
- [ ] PostgreSQL `app` role has only `CREATE`, `SELECT`, `INSERT`, `UPDATE`,
      `DELETE` on its own schema. It is **not** a superuser.
- [ ] Migration `0004` ran AND you executed the strict-mode `FORCE` block
      from §6.
- [ ] Demo seed data (`seed_screenshots.py`) is **not** present in the
      production DB. Cross-check with: `SELECT COUNT(*) FROM users
      WHERE email = 'admin@blackwoodlaw.com';` → should be 0.
- [ ] Backup job is scheduled, the cron is monitored, and a restore has
      been tested.
- [ ] Rate-limit budget (`RATE_LIMIT_PER_MINUTE`) matches your expected
      traffic profile.
- [ ] `MAX_JSON_BODY_BYTES` matches the largest legitimate request you
      expect. Upload routes are exempt — their caps live in
      `MAX_AUDIO_SIZE_BYTES` / `MAX_DOCUMENT_SIZE_BYTES`.
- [ ] WebSocket `/ws/...` endpoints require a valid JWT (regression test
      `tests/test_websocket.py::test_anonymous_reject` covers this).
- [ ] Secrets live in Azure Key Vault / AWS Secrets Manager / GCP Secret
      Manager — not in `.env` files on disk.
- [ ] Container images are pinned by digest (not by floating `:latest`).
- [ ] Audit log retention policy is documented at the organisation level
      (default 7 years per legal-product requirement NFR-15).

If any box is unchecked, you are not ready for production traffic.

---

## Public bug bounty

There is no formal bug bounty programme at this time. We do credit named
reporters in release notes (`CHANGELOG.md`) and the public advisory.

For the avoidance of doubt: testing must be against a system you operate or
where you have explicit written authorisation. Testing against any
hosted VeriDictum production tenant without authorisation is unauthorised
access and may be prosecutable.
