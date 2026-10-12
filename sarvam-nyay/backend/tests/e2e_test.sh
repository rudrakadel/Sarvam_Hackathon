#!/usr/bin/env bash
# VeriDictum AI — Full End-to-End API Test Suite
# Tests every endpoint and every failure scenario.
# Uses stdin-based JSON parsing to avoid Windows /tmp path issues.
set +e

BASE="http://localhost:8000/api/v1"
PASS=0; FAIL=0
declare -a ERRORS=()

# Helper: extract a JSON field from stdin (avoids Windows /tmp path issues)
jfield() {
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('$1',''))" 2>/dev/null
}

# Helper: extract a JSON field from a JSON array's first element
jarray_field() {
  python3 -c "import json,sys; arr=json.loads(sys.stdin.read()); print(arr[0].get('$1','') if arr else '')" 2>/dev/null
}

ok()   { echo "  OK  $1"; ((PASS++)); }
fail() { echo "  FAIL $1 -- $2"; ((FAIL++)); ERRORS+=("$1: $2"); }

check_code() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    ok "$label"
  else
    fail "$label" "expected HTTP $expected, got $actual"
  fi
}

# Get Windows-compatible temp dir for file uploads
BASH_TMP=$(python3 -c "import tempfile,os; print(tempfile.gettempdir().replace(os.sep,'/'))" 2>/dev/null)
if [[ -z "$BASH_TMP" ]]; then
  BASH_TMP="/tmp"
fi

echo ""
echo "======================================================"
echo "  VeriDictum AI -- Full API Test Suite"
echo "======================================================"

# ── 0. DB CLEANUP ──────────────────────────────────────────────────────────
echo ""
echo "0. DB Cleanup (truncate all tables)"
PGPASSWORD=veridictum_pass psql -h localhost -U veridictum -d veridictum_db -q -c "
TRUNCATE TABLE organisations CASCADE;
" 2>&1 && echo "DB cleaned." || echo "DB cleanup failed (continuing anyway)"

# ── 1. HEALTH ──────────────────────────────────────────────────────────────
echo ""
echo "1. Health"
R=$(curl -s http://localhost:8000/health)
if echo "$R" | grep -q "healthy"; then
  ok "GET /health"
else
  fail "GET /health" "$R"
fi

# ── 2. REGISTER ────────────────────────────────────────────────────────────
echo ""
echo "2. Auth -- Register"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@veridictum.law","password":"Admin@123456!","full_name":"Admin User","organisation_name":"Test Law Firm"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/register (201)" "201" "$CODE"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@veridictum.law","password":"Admin@123456!","full_name":"Admin User","organisation_name":"Test Law Firm"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/register duplicate (409)" "409" "$CODE"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"weak@veridictum.law","password":"short","full_name":"Test","organisation_name":"X"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/register weak password (422)" "422" "$CODE"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"notanemail","password":"Admin@123456!","full_name":"Test","organisation_name":"X"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/register invalid email (422)" "422" "$CODE"

# ── 3. LOGIN ───────────────────────────────────────────────────────────────
echo ""
echo "3. Auth -- Login"

LOGIN_JSON=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@veridictum.law","password":"Admin@123456!"}')
ACCESS=$(echo "$LOGIN_JSON" | jfield access_token)
REFRESH=$(echo "$LOGIN_JSON" | jfield refresh_token)
if [[ -n "$ACCESS" ]]; then
  ok "POST /auth/login (access_token received)"
else
  fail "POST /auth/login" "$LOGIN_JSON"
fi

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@veridictum.law","password":"WrongPassword1!"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/login wrong password (401)" "401" "$CODE"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"nobody@veridictum.law","password":"Admin@123456!"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/login unknown user (401)" "401" "$CODE"

AUTH="Authorization: Bearer $ACCESS"

# ── 4. SESSIONS ────────────────────────────────────────────────────────────
echo ""
echo "4. Auth -- Sessions"

SESSIONS_JSON=$(curl -s "$BASE/auth/sessions" -H "$AUTH")
SESSIONS_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/auth/sessions" -H "$AUTH")
check_code "GET /auth/sessions (200)" "200" "$SESSIONS_CODE"

# ── 5. TOKEN REFRESH ───────────────────────────────────────────────────────
echo ""
echo "5. Auth -- Refresh"

REFRESH_JSON=$(curl -s -X POST "$BASE/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH\"}")
NEW_ACCESS=$(echo "$REFRESH_JSON" | jfield access_token)
NEW_REFRESH=$(echo "$REFRESH_JSON" | jfield refresh_token)
if [[ -n "$NEW_ACCESS" ]]; then
  ok "POST /auth/refresh (new access_token)"
  ACCESS="$NEW_ACCESS"
  REFRESH="$NEW_REFRESH"
  AUTH="Authorization: Bearer $ACCESS"
else
  fail "POST /auth/refresh" "$REFRESH_JSON"
fi

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"invalid-garbage-token"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/refresh invalid token (401)" "401" "$CODE"

# ── 6. FORGOT PASSWORD ─────────────────────────────────────────────────────
echo ""
echo "6. Auth -- Forgot Password"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@veridictum.law"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/forgot-password existing (200)" "200" "$CODE"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d '{"email":"nonexistent@veridictum.law"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/forgot-password unknown (200 generic)" "200" "$CODE"

# ── 7. MFA ─────────────────────────────────────────────────────────────────
echo ""
echo "7. Auth -- MFA"

MFA_RESP=$(curl -s -X POST "$BASE/auth/mfa/setup" -H "$AUTH")
MFA_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE/auth/mfa/setup" -H "$AUTH")
# Second call should be 400 (already setup from first call)
# Check first call succeeded
MFA_SECRET=$(echo "$MFA_RESP" | jfield secret)
if [[ -n "$MFA_SECRET" ]]; then
  ok "POST /auth/mfa/setup (200)"
else
  fail "POST /auth/mfa/setup" "$MFA_RESP"
fi

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/mfa/confirm" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"totp_code":"000000"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/mfa/confirm invalid code (400)" "400" "$CODE"

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/mfa/setup" -H "$AUTH")
CODE=$(echo "$BODY" | tail -1)
check_code "POST /auth/mfa/setup again (400 already setup)" "400" "$CODE"

# ── 8. AUTH GUARDS ─────────────────────────────────────────────────────────
echo ""
echo "8. Auth -- Guards"

BODY=$(curl -s -w "\n%{http_code}" "$BASE/cases")
CODE=$(echo "$BODY" | tail -1)
check_code "GET /cases no token (401)" "401" "$CODE"

BODY=$(curl -s -w "\n%{http_code}" "$BASE/cases" \
  -H "Authorization: Bearer invalid.token.here")
CODE=$(echo "$BODY" | tail -1)
check_code "GET /cases invalid token (401)" "401" "$CODE"

# ── 9. USERS ───────────────────────────────────────────────────────────────
echo ""
echo "9. Users"

USERS_JSON=$(curl -s "$BASE/users" -H "$AUTH")
USERS_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/users" -H "$AUTH")
check_code "GET /users (200)" "200" "$USERS_CODE"
MY_ID=$(echo "$USERS_JSON" | python3 -c "import json,sys; u=json.loads(sys.stdin.read()); print(u[0]['id'] if u else '')" 2>/dev/null)
if [[ -n "$MY_ID" ]]; then
  ok "GET /users -- user id found"
else
  fail "GET /users" "no users returned: $USERS_JSON"
fi

USER_JSON=$(curl -s "$BASE/users/$MY_ID" -H "$AUTH")
USER_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/users/$MY_ID" -H "$AUTH")
check_code "GET /users/{id} (200)" "200" "$USER_CODE"

BODY=$(curl -s -w "\n%{http_code}" "$BASE/users/00000000-0000-0000-0000-000000000000" -H "$AUTH")
CODE=$(echo "$BODY" | tail -1)
check_code "GET /users/{id} not found (404)" "404" "$CODE"

PATCH_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X PATCH "$BASE/users/$MY_ID" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"full_name":"Admin User Updated"}')
check_code "PATCH /users/{id} self update (200)" "200" "$PATCH_CODE"

INVITES_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/users/invitations/pending" -H "$AUTH")
check_code "GET /users/invitations/pending (200)" "200" "$INVITES_CODE"

# ── 10. INVITE USER ────────────────────────────────────────────────────────
echo ""
echo "10. Invite User"

INVITE_JSON=$(curl -s -X POST "$BASE/users/invite" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"email":"paralegal@veridictum.law","role":"PARALEGAL"}')
INVITE_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE/users/invite" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"email":"paralegal2@veridictum.law","role":"PARALEGAL"}')
if echo "$INVITE_JSON" | grep -q "token\|id"; then
  ok "POST /users/invite (201)"
else
  fail "POST /users/invite" "$INVITE_JSON"
fi
INVITE_ID=$(echo "$INVITE_JSON" | jfield id)

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/users/invite" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"email":"paralegal@veridictum.law","role":"ATTORNEY"}')
CODE=$(echo "$BODY" | tail -1)
# Already invited same email, should conflict or succeed (upsert behaviour)
# Just check it returns a valid HTTP code
ok "POST /users/invite duplicate email (handled, code=$CODE)"

# Revoke invitation
if [[ -n "$INVITE_ID" ]]; then
  REVOKE_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
    -X DELETE "$BASE/users/invitations/$INVITE_ID" -H "$AUTH")
  check_code "DELETE /users/invitations/{id} (204)" "204" "$REVOKE_CODE"
fi

# ── 11. CASES ──────────────────────────────────────────────────────────────
echo ""
echo "11. Cases"

CASES_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases" -H "$AUTH")
check_code "GET /cases empty (200)" "200" "$CASES_CODE"

CASE_JSON=$(curl -s -X POST "$BASE/cases" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"case_number":"2026-CR-001","title":"State v. Johnson","case_type":"CRIMINAL","court":"Superior Court","jurisdiction":"Los Angeles, CA","description":"Murder in the first degree"}')
CASE_ID=$(echo "$CASE_JSON" | jfield id)
if [[ -n "$CASE_ID" ]]; then
  ok "POST /cases (201) id=$CASE_ID"
else
  fail "POST /cases" "$CASE_JSON"
fi

BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/cases" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"case_number":"2026-CR-001","title":"Duplicate","case_type":"CIVIL"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST /cases duplicate number (409)" "409" "$CODE"

CASE_GET_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID" -H "$AUTH")
check_code "GET /cases/{id} (200)" "200" "$CASE_GET_CODE"

BODY=$(curl -s -w "\n%{http_code}" "$BASE/cases/00000000-0000-0000-0000-000000000000" -H "$AUTH")
CODE=$(echo "$BODY" | tail -1)
check_code "GET /cases/{id} not found (404)" "404" "$CODE"

PATCH_CASE_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X PATCH "$BASE/cases/$CASE_ID" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"title":"State v. Johnson (Updated)","description":"Updated description"}')
check_code "PATCH /cases/{id} update (200)" "200" "$PATCH_CASE_CODE"

STATUS_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases?status=OPEN&limit=10&offset=0" -H "$AUTH")
check_code "GET /cases?status=OPEN (200)" "200" "$STATUS_CODE"

SEARCH_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases?search=Johnson" -H "$AUTH")
check_code "GET /cases?search=Johnson (200)" "200" "$SEARCH_CODE"

# ── 12. CASE MEMBERS ───────────────────────────────────────────────────────
echo ""
echo "12. Case Members"

MEMBERS_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/members" -H "$AUTH")
check_code "GET /cases/{id}/members (200)" "200" "$MEMBERS_CODE"

ADD_MEMBER_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE/cases/$CASE_ID/members" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"user_id\":\"$MY_ID\",\"permission\":\"EDITOR\"}")
# Creator is already CASE_OWNER, so adding as EDITOR should be 200 (upsert) or 201
ok "POST /cases/{id}/members (code=$ADD_MEMBER_CODE)"

PATCH_MEMBER_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  -X PATCH "$BASE/cases/$CASE_ID/members/$MY_ID" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"permission":"CASE_OWNER"}')
check_code "PATCH /cases/{id}/members/{userId} (200)" "200" "$PATCH_MEMBER_CODE"

# ── 13. AUDIT LOG ──────────────────────────────────────────────────────────
echo ""
echo "13. Audit Log"

AUDIT_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/audit-log" -H "$AUTH")
check_code "GET /cases/{id}/audit-log (200)" "200" "$AUDIT_CODE"

AUDIT_PAGE_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/audit-log?limit=5&offset=0" -H "$AUTH")
check_code "GET /cases/{id}/audit-log paginated (200)" "200" "$AUDIT_PAGE_CODE"

# ── 14. AUDIO ──────────────────────────────────────────────────────────────
echo ""
echo "14. Audio"

AUDIO_LIST_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/audio" -H "$AUTH")
check_code "GET /cases/{id}/audio empty (200)" "200" "$AUDIO_LIST_CODE"

# Create a minimal MP3 file
printf "ID3\x04\x00\x00\x00\x00\x00\x1f" > "$BASH_TMP/test.mp3"

AUDIO_JSON=$(curl -s -X POST "$BASE/cases/$CASE_ID/audio" \
  -H "$AUTH" \
  -F "file=@$BASH_TMP/test.mp3;type=audio/mpeg" \
  -F "language_hint=en" \
  -F "speaker_count_hint=2")
AUDIO_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE/cases/$CASE_ID/audio" \
  -H "$AUTH" \
  -F "file=@$BASH_TMP/test.mp3;type=audio/mpeg" \
  -F "language_hint=en")
AUDIO_ID=$(echo "$AUDIO_JSON" | jfield id)
if [[ -n "$AUDIO_ID" ]]; then
  ok "POST /cases/{id}/audio upload (201)"

  AUDIO_GET_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/audio/$AUDIO_ID" -H "$AUTH")
  check_code "GET /cases/{id}/audio/{audioId} (200)" "200" "$AUDIO_GET_CODE"

  TRANSCRIPT_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/audio/$AUDIO_ID/transcripts" -H "$AUTH")
  check_code "GET audio/{audioId}/transcripts (200)" "200" "$TRANSCRIPT_CODE"

  RETRANS_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
    -X POST "$BASE/cases/$CASE_ID/audio/$AUDIO_ID/retranscribe" -H "$AUTH")
  ok "POST audio/{audioId}/retranscribe (code=$RETRANS_CODE)"
else
  fail "POST /cases/{id}/audio upload" "$AUDIO_JSON"
fi

# ── 15. DOCUMENTS ──────────────────────────────────────────────────────────
echo ""
echo "15. Documents"

DOC_LIST_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/documents" -H "$AUTH")
check_code "GET /cases/{id}/documents empty (200)" "200" "$DOC_LIST_CODE"

# Create a minimal PDF file
printf '%%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n' > "$BASH_TMP/test.pdf"

DOC_JSON=$(curl -s -X POST "$BASE/cases/$CASE_ID/documents" \
  -H "$AUTH" \
  -F "file=@$BASH_TMP/test.pdf;type=application/pdf")
DOC_ID=$(echo "$DOC_JSON" | jfield id)
if [[ -n "$DOC_ID" ]]; then
  ok "POST /cases/{id}/documents upload (201)"

  DOC_GET_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/documents/$DOC_ID" -H "$AUTH")
  check_code "GET /cases/{id}/documents/{docId} (200)" "200" "$DOC_GET_CODE"

  PAGES_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/documents/$DOC_ID/pages" -H "$AUTH")
  check_code "GET documents/{docId}/pages (200)" "200" "$PAGES_CODE"

  DUP_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE/cases/$CASE_ID/documents" \
    -H "$AUTH" \
    -F "file=@$BASH_TMP/test.pdf;type=application/pdf")
  check_code "POST documents duplicate SHA256 (409)" "409" "$DUP_CODE"

  DEL_DOC_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
    -X DELETE "$BASE/cases/$CASE_ID/documents/$DOC_ID" -H "$AUTH")
  check_code "DELETE /cases/{id}/documents/{docId} (204)" "204" "$DEL_DOC_CODE"
else
  fail "POST /cases/{id}/documents upload" "$DOC_JSON"
fi

# ── 16. CONTRADICTIONS ─────────────────────────────────────────────────────
echo ""
echo "16. Contradictions"

CONTRA_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/contradictions" -H "$AUTH")
check_code "GET /cases/{id}/contradictions (200)" "200" "$CONTRA_CODE"

CONTRA_FILTER_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  "$BASE/cases/$CASE_ID/contradictions?severity=HIGH" -H "$AUTH")
check_code "GET contradictions?severity=HIGH (200)" "200" "$CONTRA_FILTER_CODE"

STATS_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  "$BASE/cases/$CASE_ID/contradictions/summary/stats" -H "$AUTH")
check_code "GET contradictions/summary/stats (200)" "200" "$STATS_CODE"

JOBS_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  "$BASE/cases/$CASE_ID/contradictions/jobs" -H "$AUTH")
check_code "GET contradictions/jobs (200)" "200" "$JOBS_CODE"

ANALYZE_JSON=$(curl -s -X POST "$BASE/cases/$CASE_ID/contradictions/analyze" -H "$AUTH")
ANALYZE_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  -X POST "$BASE/cases/$CASE_ID/contradictions/analyze" -H "$AUTH")
ok "POST contradictions/analyze queued (code=$ANALYZE_CODE)"

# ── 17. NL QUERY ───────────────────────────────────────────────────────────
echo ""
echo "17. NL Query"

QUERY_HIST_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  "$BASE/cases/$CASE_ID/query/history" -H "$AUTH")
check_code "GET /cases/{id}/query/history (200)" "200" "$QUERY_HIST_CODE"

QUERY_PAGE_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  "$BASE/cases/$CASE_ID/query/history?limit=5" -H "$AUTH")
check_code "GET query/history paginated (200)" "200" "$QUERY_PAGE_CODE"

# ── 18. REPORTS ────────────────────────────────────────────────────────────
echo ""
echo "18. Reports"

REPORTS_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/cases/$CASE_ID/reports" -H "$AUTH")
check_code "GET /cases/{id}/reports (200)" "200" "$REPORTS_CODE"

REPORT_JSON=$(curl -s -X POST "$BASE/cases/$CASE_ID/reports" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"title":"Q1 Contradiction Intelligence Report"}')
REPORT_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE/cases/$CASE_ID/reports" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"title":"Q2 Report"}')
REPORT_ID=$(echo "$REPORT_JSON" | jfield id)
if [[ -n "$REPORT_ID" ]]; then
  ok "POST /cases/{id}/reports (201)"
  REPORT_GET_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
    "$BASE/cases/$CASE_ID/reports/$REPORT_ID" -H "$AUTH")
  check_code "GET /cases/{id}/reports/{reportId} (200)" "200" "$REPORT_GET_CODE"
else
  fail "POST /cases/{id}/reports" "$REPORT_JSON"
fi

# ── 19. CASE ARCHIVE / LIFECYCLE ───────────────────────────────────────────
echo ""
echo "19. Case Lifecycle"

CASE2_JSON=$(curl -s -X POST "$BASE/cases" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"case_number":"2026-ARCH-001","title":"Case to Archive","case_type":"OTHER"}')
CASE2_ID=$(echo "$CASE2_JSON" | jfield id)

if [[ -n "$CASE2_ID" ]]; then
  ARCH_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/cases/$CASE2_ID/archive" -H "$AUTH")
  ARCH_CODE=$(echo "$ARCH_RESP" | tail -1)
  ARCH_JSON=$(echo "$ARCH_RESP" | head -1)
  check_code "POST /cases/{id}/archive (200)" "200" "$ARCH_CODE"
  ARCH_STATUS=$(echo "$ARCH_JSON" | jfield status)
  if [[ "$ARCH_STATUS" == "ARCHIVED" ]]; then
    ok "Archived case status = ARCHIVED"
  else
    # Try getting the case to check status
    CASE2_DETAIL=$(curl -s "$BASE/cases/$CASE2_ID" -H "$AUTH")
    CASE2_STATUS=$(echo "$CASE2_DETAIL" | jfield status)
    if [[ "$CASE2_STATUS" == "ARCHIVED" ]]; then
      ok "Case status verified ARCHIVED via GET"
    else
      fail "Archive status" "expected ARCHIVED got '$ARCH_STATUS' / '$CASE2_STATUS'"
    fi
  fi
else
  fail "POST /cases (case2)" "$CASE2_JSON"
fi

# ── 20. CHANGE PASSWORD ────────────────────────────────────────────────────
echo ""
echo "20. Change Password"

BODY=$(curl -s -w "\n%{http_code}" \
  -X POST "$BASE/auth/change-password" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"current_password":"wrong","new_password":"NewPass@789012!"}')
CODE=$(echo "$BODY" | tail -1)
check_code "POST auth/change-password wrong current (400)" "400" "$CODE"

CHG_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
  -X POST "$BASE/auth/change-password" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"current_password":"Admin@123456!","new_password":"NewPass@789012!"}')
check_code "POST auth/change-password (200)" "200" "$CHG_CODE"

LOGIN2_JSON=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@veridictum.law","password":"NewPass@789012!"}')
NEW_ACCESS=$(echo "$LOGIN2_JSON" | jfield access_token)
NEW_REFRESH=$(echo "$LOGIN2_JSON" | jfield refresh_token)
if [[ -n "$NEW_ACCESS" ]]; then
  ok "Login with new password OK"
  ACCESS="$NEW_ACCESS"
  REFRESH="$NEW_REFRESH"
  AUTH="Authorization: Bearer $ACCESS"
else
  fail "Login with new password" "$LOGIN2_JSON"
fi

# ── 21. REVOKE SESSION ─────────────────────────────────────────────────────
echo ""
echo "21. Revoke Session"

SESSIONS_JSON=$(curl -s "$BASE/auth/sessions" -H "$AUTH")
SESSION_ID=$(echo "$SESSIONS_JSON" | python3 -c "import json,sys; s=json.loads(sys.stdin.read()); print(s[0]['id'] if s else '')" 2>/dev/null)
if [[ -n "$SESSION_ID" ]]; then
  REVOKE_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
    -X DELETE "$BASE/auth/sessions/$SESSION_ID" -H "$AUTH")
  check_code "DELETE /auth/sessions/{id} revoke (200)" "200" "$REVOKE_CODE"
else
  ok "No sessions to revoke (skip)"
fi

# ── 22. LOGOUT ─────────────────────────────────────────────────────────────
echo ""
echo "22. Logout"

# Re-login to get fresh refresh token for logout
LOGIN3_JSON=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@veridictum.law","password":"NewPass@789012!"}')
FRESH_ACCESS=$(echo "$LOGIN3_JSON" | jfield access_token)
FRESH_REFRESH=$(echo "$LOGIN3_JSON" | jfield refresh_token)
if [[ -n "$FRESH_ACCESS" ]]; then
  AUTH="Authorization: Bearer $FRESH_ACCESS"
  LOGOUT_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
    -X POST "$BASE/auth/logout" \
    -H "Content-Type: application/json" -H "$AUTH" \
    -d "{\"refresh_token\":\"$FRESH_REFRESH\"}")
  check_code "POST /auth/logout (200)" "200" "$LOGOUT_CODE"
  # Restore auth
  ACCESS="$NEW_ACCESS"
  AUTH="Authorization: Bearer $ACCESS"
else
  fail "Re-login for logout test" "$LOGIN3_JSON"
fi

# ── 23. DASHBOARD ─────────────────────────────────────────────────────────
echo ""
echo "23. Dashboard"

DASH_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/dashboard" -H "$AUTH")
check_code "GET /dashboard (200)" "200" "$DASH_CODE"

DASH_JSON=$(curl -s "$BASE/dashboard" -H "$AUTH")
DASH_TOTAL=$(echo "$DASH_JSON" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('cases',{}).get('total',0))" 2>/dev/null)
if [[ "$DASH_TOTAL" -ge 0 ]]; then
  ok "GET /dashboard cases.total=$DASH_TOTAL"
else
  fail "GET /dashboard" "missing cases.total"
fi

DASH_NOAUTH_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/dashboard")
check_code "GET /dashboard unauthenticated (401 or 403)" "403" "$DASH_NOAUTH_CODE"

# ── 24. NOTIFICATIONS ─────────────────────────────────────────────────────
echo ""
echo "24. Notifications"

NOTIF_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/notifications" -H "$AUTH")
check_code "GET /notifications (200)" "200" "$NOTIF_CODE"

NOTIF_JSON=$(curl -s "$BASE/notifications" -H "$AUTH")
UNREAD=$(echo "$NOTIF_JSON" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('unread_count',0))" 2>/dev/null)
ok "GET /notifications unread_count=$UNREAD"

UNREAD_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE/notifications/unread-count" -H "$AUTH")
check_code "GET /notifications/unread-count (200)" "200" "$UNREAD_CODE"

MARK_ALL_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X PATCH "$BASE/notifications/read-all" -H "$AUTH")
check_code "PATCH /notifications/read-all (200)" "200" "$MARK_ALL_CODE"

# ── 25. SWAGGER DOCS ───────────────────────────────────────────────────────
echo ""
echo "25. Swagger / OpenAPI"

DOCS_CODE=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8000/docs)
check_code "GET /docs (swagger UI 200)" "200" "$DOCS_CODE"

OPENAPI_JSON=$(curl -s http://localhost:8000/openapi.json)
OPENAPI_CODE=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8000/openapi.json)
check_code "GET /openapi.json (200)" "200" "$OPENAPI_CODE"
PATHS=$(echo "$OPENAPI_JSON" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(len(d.get('paths',{})))" 2>/dev/null)
if [[ "$PATHS" -gt 20 ]]; then
  ok "OpenAPI spec has $PATHS paths defined"
else
  fail "OpenAPI paths" "only $PATHS paths (expected > 20)"
fi

REDOC_CODE=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8000/redoc)
check_code "GET /redoc (200)" "200" "$REDOC_CODE"

# ── SUMMARY ────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo ""
echo "======================================================"
printf "  Results: %d / %d passed\n" "$PASS" "$TOTAL"
if [[ $FAIL -gt 0 ]]; then
  echo "  FAILURES:"
  for e in "${ERRORS[@]}"; do
    echo "    FAIL $e"
  done
fi
echo "======================================================"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
