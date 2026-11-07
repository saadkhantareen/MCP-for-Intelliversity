# FINAL INTEGRATION TEST — Checkpoint 10-11, hit the real API.
#
# Prereqs:
#   1. python manage.py runserver
#   2. These UniversityDomain rows exist for the comsats tenant (see README):
#        faculty.comsats.localhost
#        student.comsats.localhost
#        admin.comsats.localhost   (optional, only needed if you add admin checks)
#   3. faculty.comsats.localhost / student.comsats.localhost resolve to
#      127.0.0.1 — either via /etc/hosts entries, or rely on the fact that
#      *.localhost already resolves to 127.0.0.1 on most systems (no /etc/hosts
#      edit needed on Linux/macOS with a modern glibc/nsswitch; if curl fails
#      to connect at all rather than 404ing, add explicit /etc/hosts entries).
#   4. Tokens: OPTIONAL to set manually. If FACULTY_TOKEN/STUDENT_TOKEN
#      aren't already exported, this script mints them itself on every run
#      (see the block right after `set -uo pipefail` below). You only need
#      to export them yourself if you want to reuse a specific token across
#      multiple runs instead of getting a fresh one each time.
#
# IMPORTANT: tenant AND portal are both resolved from a single exact-match
# lookup on UniversityDomain.domain (apps/tenants/utils/domain_utils.py).
# There is no single shared host for "the comsats tenant" — each portal has
# its own domain. Faculty requests MUST use the faculty host; student
# requests MUST use the student host, or you get 404 {"detail":"Invalid domain."}
# before the request ever reaches urls.py/views.py.

set -uo pipefail

FACULTY_BASE="http://faculty.comsats.localhost:8000/api/v1/attendance"
STUDENT_BASE="http://student.comsats.localhost:8000/api/v1/attendance"

# ---------------------------------------------------------------------------
# Auto-mint tokens if not already exported. This removes the manual
# "run one command, copy its output, paste into another command" step
# entirely — the single most common way this has broken in testing.
# Uses `shell -c` (not a heredoc) specifically because `shell -c` does NOT
# print the "N objects imported automatically" banner that heredoc mode
# does — that banner text was liable to get swept up by any $(...) capture.
# ---------------------------------------------------------------------------
if [[ -z "${FACULTY_TOKEN:-}" || -z "${STUDENT_TOKEN:-}" ]]; then
  echo "FACULTY_TOKEN/STUDENT_TOKEN not set — minting them now..."
  TOKEN_OUTPUT=$(python manage.py shell -c "
from apps.tenants.models import University
from apps.tenants.utils.db_utils import ensure_tenant_db_configured, close_tenant_db_connection
from apps.tenants.context import set_current_tenant, clear_current_tenant
from django.db import connections
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

uni = University.objects.get(subdomain='comsats')
db_key = ensure_tenant_db_configured(uni)
connections[db_key].ensure_connection()
set_current_tenant(uni)

User = get_user_model()
faculty = User.objects.using(db_key).filter(groups__name='faculty').first()
student = User.objects.using(db_key).filter(groups__name='student').first()

if faculty:
    print('FACULTY_TOKEN=' + str(RefreshToken.for_user(faculty).access_token))
if student:
    print('STUDENT_TOKEN=' + str(RefreshToken.for_user(student).access_token))

clear_current_tenant()
close_tenant_db_connection(db_key)
")
  # Extract just the two assignment lines, ignore anything else printed.
  MINTED_FACULTY=$(echo "$TOKEN_OUTPUT" | grep '^FACULTY_TOKEN=' | cut -d= -f2-)
  MINTED_STUDENT=$(echo "$TOKEN_OUTPUT" | grep '^STUDENT_TOKEN=' | cut -d= -f2-)

  if [[ -z "$MINTED_FACULTY" ]]; then
    echo "FATAL: could not mint a faculty token — no faculty user found. Seed dummy data first." >&2
    echo "--- raw shell output for debugging ---" >&2
    echo "$TOKEN_OUTPUT" >&2
    exit 1
  fi
  if [[ -z "$MINTED_STUDENT" ]]; then
    echo "FATAL: could not mint a student token — no student user found. Seed dummy data first." >&2
    echo "--- raw shell output for debugging ---" >&2
    echo "$TOKEN_OUTPUT" >&2
    exit 1
  fi

  FACULTY_TOKEN="${FACULTY_TOKEN:-$MINTED_FACULTY}"
  STUDENT_TOKEN="${STUDENT_TOKEN:-$MINTED_STUDENT}"
  echo "  faculty token: ${FACULTY_TOKEN:0:20}..."
  echo "  student token: ${STUDENT_TOKEN:0:20}..."
  echo
fi

HF="Authorization: Bearer ${FACULTY_TOKEN:?set FACULTY_TOKEN first}"
HS="Authorization: Bearer ${STUDENT_TOKEN:?set STUDENT_TOKEN first}"

pass=0
fail=0
check() {
  local desc="$1" expect="$2" got="$3"
  if [[ "$got" == "$expect" ]]; then
    echo "  PASS  $desc (got $got)"
    pass=$((pass+1))
  else
    echo "  FAIL  $desc (expected $expect, got $got)"
    fail=$((fail+1))
  fi
}

echo "======================================================================"
echo "F1 — faculty: my classes today"
echo "======================================================================"
TODAY=$(curl -s -o /tmp/today.json -w "%{http_code}" -H "$HF" "$FACULTY_BASE/sessions/today/")
check "GET /sessions/today/" 200 "$TODAY"
cat /tmp/today.json | jq '.[0].id // "no sessions today"'

echo
echo "======================================================================"
echo "F3 — faculty: roster for a session"
echo "======================================================================"
SID=$(curl -s -H "$HF" "$FACULTY_BASE/sessions/?page_size=1" | jq -r 'if type=="array" then .[0].id elif type=="object" then .results[0].id else empty end')
if [[ -z "$SID" ]]; then
  echo "  SKIP — faculty has no visible sessions; seed dummy data first."
else
  echo "  using session: $SID"
  ROSTER=$(curl -s -o /tmp/roster.json -w "%{http_code}" -H "$HF" "$FACULTY_BASE/sessions/$SID/roster/")
  check "GET /sessions/$SID/roster/" 200 "$ROSTER"
  jq '.students[0], .policy' /tmp/roster.json

  echo
  echo "======================================================================"
  echo "F3 — faculty: bulk mark (must be idempotent — BR4)"
  echo "======================================================================"
  ENROLLMENT=$(jq -r '.students[0].enrollment_id // empty' /tmp/roster.json)
  if [[ -n "$ENROLLMENT" ]]; then
    BODY=$(cat <<JSON
{"topic":"AVL rotations","records":[{"enrollment":"$ENROLLMENT","status":"present"}]}
JSON
)
    R1=$(curl -s -X POST -H "$HF" -H "Content-Type: application/json" -d "$BODY" "$FACULTY_BASE/sessions/$SID/mark/")
    echo "  first call:  $R1"
    R2=$(curl -s -X POST -H "$HF" -H "Content-Type: application/json" -d "$BODY" "$FACULTY_BASE/sessions/$SID/mark/")
    echo "  second call: $R2"
    CREATED2=$(echo "$R2" | jq -r '.created')
    UPDATED2=$(echo "$R2" | jq -r '.updated')
    check "idempotency: second call created=0" "0" "$CREATED2"
    echo "  (second call updated=$UPDATED2 — nonzero is fine, that's the upsert; created must be 0)"
  else
    echo "  SKIP — no enrolled students on this session's roster."
  fi

  echo
  echo "======================================================================"
  echo "STUDENT — must be forbidden from marking (hit via STUDENT_BASE)"
  echo "======================================================================"
  SCODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$HS" \
    -H "Content-Type: application/json" -d '{"records":[]}' \
    "$STUDENT_BASE/sessions/$SID/mark/")
  check "student POST /mark/ -> 403" 403 "$SCODE"
fi

echo
echo "======================================================================"
echo "STUDENT — my summary and my records (must show ONLY own data)"
echo "======================================================================"
SUMM=$(curl -s -o /tmp/summary.json -w "%{http_code}" -H "$HS" "$STUDENT_BASE/summary/me/")
check "GET /summary/me/" 200 "$SUMM"
cat /tmp/summary.json | jq

RECS=$(curl -s -o /tmp/records.json -w "%{http_code}" -H "$HS" "$STUDENT_BASE/records/")
check "GET /records/" 200 "$RECS"
echo "  record count visible to this student: $(jq 'if type=="object" then .count else length end' /tmp/records.json)"

echo
echo "======================================================================"
echo "A5 — defaulters report (faculty, scoped to a course_offering)"
echo "======================================================================"
if [[ -n "${SID:-}" ]]; then
  OFFERING=$(curl -s -H "$HF" "$FACULTY_BASE/sessions/$SID/" | jq -r '.course_offering')
  DEF=$(curl -s -o /tmp/defaulters.json -w "%{http_code}" -H "$HF" \
    "$FACULTY_BASE/reports/defaulters/?course_offering=$OFFERING")
  check "GET /reports/defaulters/" 200 "$DEF"
  jq '.count' /tmp/defaulters.json
fi

echo
echo "======================================================================"
echo "SUMMARY"
echo "======================================================================"
echo "  passed: $pass"
echo "  failed: $fail"
[[ $fail -eq 0 ]] && exit 0 || exit 1
