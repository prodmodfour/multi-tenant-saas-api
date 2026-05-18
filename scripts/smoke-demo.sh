#!/usr/bin/env bash
set -euo pipefail

# Run a public-safe local smoke demo against the Docker Compose API.
# Start the stack first with: docker compose up --build
#
# The script uses deterministic placeholder users for the selected run ID and
# never prints bearer tokens, demo passwords, or raw API key material.

BASE_URL="${SAAS_API_DEMO_BASE_URL:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"
DEMO_RUN_ID="${SAAS_API_DEMO_RUN_ID:-$(date -u +%Y%m%d%H%M%S)-${RANDOM}}"
DEMO_RUN_SLUG="$(printf '%s' "${DEMO_RUN_ID}" | tr '[:upper:]' '[:lower:]')"

if [[ ! "${DEMO_RUN_SLUG}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "SAAS_API_DEMO_RUN_ID must contain only slug-safe letters, numbers, and single hyphens." >&2
  exit 2
fi

OWNER_EMAIL="owner-${DEMO_RUN_SLUG}@example.com"
MEMBER_EMAIL="member-${DEMO_RUN_SLUG}@example.com"
OWNER_PASSWORD="local-placeholder-demo-password-${DEMO_RUN_SLUG}-owner"
MEMBER_PASSWORD="local-placeholder-demo-password-${DEMO_RUN_SLUG}-member"
ORG_SLUG="demo-${DEMO_RUN_SLUG}"

LAST_RESPONSE_BODY=""
LAST_STATUS_CODE=""

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 2
  fi
}

redact_response_body() {
  python3 -c '
import json
import sys

body = sys.stdin.read()
secret_markers = (
    "authorization",
    "password",
    "raw_key",
    "secret",
    "token",
    "key_hash",
)


def redact(value):
    if isinstance(value, dict):
        redacted = {}
        for key, nested in value.items():
            normalised_key = key.lower()
            if any(marker in normalised_key for marker in secret_markers):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact(nested)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value

try:
    decoded = json.loads(body)
except json.JSONDecodeError:
    print(body[:2000])
else:
    print(json.dumps(redact(decoded), indent=2, sort_keys=True)[:2000])
' <<<"${LAST_RESPONSE_BODY}"
}

api_request() {
  local method="$1"
  local path="$2"
  local expected_status="$3"
  local request_body="${4:-}"
  local auth_token="${5:-}"
  local idempotency_key="${6:-}"
  local response
  local -a curl_args

  curl_args=(
    --silent
    --show-error
    --request "${method}"
    --header "Accept: application/json"
    --write-out $'\n%{http_code}'
  )

  if [[ -n "${request_body}" ]]; then
    curl_args+=(--header "Content-Type: application/json" --data-binary @-)
  fi
  if [[ -n "${auth_token}" ]]; then
    curl_args+=(--header "Authorization: Bearer ${auth_token}")
  fi
  if [[ -n "${idempotency_key}" ]]; then
    curl_args+=(--header "Idempotency-Key: ${idempotency_key}")
  fi

  if [[ -n "${request_body}" ]]; then
    if ! response="$(printf '%s' "${request_body}" | curl "${curl_args[@]}" "${BASE_URL}${path}")"; then
      echo "Request failed before an HTTP response was received: ${method} ${path}" >&2
      exit 1
    fi
  elif ! response="$(curl "${curl_args[@]}" "${BASE_URL}${path}")"; then
    echo "Request failed before an HTTP response was received: ${method} ${path}" >&2
    exit 1
  fi

  LAST_STATUS_CODE="${response##*$'\n'}"
  LAST_RESPONSE_BODY="${response%$'\n'*}"

  if [[ "${LAST_STATUS_CODE}" != "${expected_status}" ]]; then
    echo "Unexpected status for ${method} ${path}: got ${LAST_STATUS_CODE}, expected ${expected_status}." >&2
    echo "Redacted response body:" >&2
    redact_response_body >&2
    exit 1
  fi
}

json_get() {
  local json_path="$1"
  python3 -c '
import json
import sys

data = json.load(sys.stdin)
value = data
for part in sys.argv[1].split("."):
    if not part:
        continue
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value[part]
if value is None:
    print("")
else:
    print(value)
' "${json_path}" <<<"${LAST_RESPONSE_BODY}"
}

print_audit_summary() {
  python3 -c '
import json
import sys

data = json.load(sys.stdin)
items = data.get("items", [])
if not items:
    print("No audit events returned.")
    raise SystemExit(0)
print("Latest audit events:")
for item in items[:8]:
    created_at = item["created_at"]
    action = item["action"]
    target_type = item["target_type"]
    print(f"- {created_at} {action} {target_type}")
' <<<"${LAST_RESPONSE_BODY}"
}

wait_for_readiness() {
  echo "Waiting for ${BASE_URL}/readyz ..."
  for _ in {1..60}; do
    if curl --fail --silent --show-error "${BASE_URL}/readyz" >/dev/null 2>&1; then
      echo "API is ready."
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for the API to become ready." >&2
  echo "Start the local stack with: docker compose up --build" >&2
  exit 1
}

require_command curl
require_command python3

cat <<EOF
Running public-safe smoke demo against ${BASE_URL}
Run ID: ${DEMO_RUN_SLUG}

The script will not print demo passwords, bearer tokens, or raw API key material.
EOF

wait_for_readiness

printf '\n[1/12] Register owner user...\n'
api_request "POST" "/auth/register" "201" "$(cat <<JSON
{"email":"${OWNER_EMAIL}","password":"${OWNER_PASSWORD}","display_name":"Demo Owner ${DEMO_RUN_SLUG}"}
JSON
)"
owner_user_id="$(json_get "user.id")"
echo "Registered owner user ${owner_user_id}."

printf '\n[2/12] Login owner user...\n'
api_request "POST" "/auth/login" "200" "$(cat <<JSON
{"email":"${OWNER_EMAIL}","password":"${OWNER_PASSWORD}"}
JSON
)"
owner_access_token="$(json_get "access_token")"
echo "Owner login succeeded; bearer token captured in memory only."

printf '\n[3/12] Create organisation tenant...\n'
api_request "POST" "/orgs" "201" "$(cat <<JSON
{"name":"Demo Organisation ${DEMO_RUN_SLUG}","slug":"${ORG_SLUG}"}
JSON
)" "${owner_access_token}" "demo-org-${DEMO_RUN_SLUG}"
organisation_id="$(json_get "id")"
echo "Created organisation ${organisation_id}."

printf '\n[4/12] Register second user...\n'
api_request "POST" "/auth/register" "201" "$(cat <<JSON
{"email":"${MEMBER_EMAIL}","password":"${MEMBER_PASSWORD}","display_name":"Demo Member ${DEMO_RUN_SLUG}"}
JSON
)"
member_user_id="$(json_get "user.id")"
echo "Registered second user ${member_user_id}."

printf '\n[5/12] Add second user as an organisation member...\n'
api_request "POST" "/orgs/${organisation_id}/members" "201" "$(cat <<JSON
{"user_id":"${member_user_id}","role":"member"}
JSON
)" "${owner_access_token}"
echo "Added member ${member_user_id} to organisation ${organisation_id}."

printf '\n[6/12] Create project...\n'
api_request "POST" "/orgs/${organisation_id}/projects" "201" "$(cat <<JSON
{"name":"Launch Checklist ${DEMO_RUN_SLUG}","description":"Public-safe smoke demo project","status":"active"}
JSON
)" "${owner_access_token}" "demo-project-${DEMO_RUN_SLUG}"
project_id="$(json_get "id")"
echo "Created project ${project_id}."

printf '\n[7/12] List projects with pagination, filtering, and sorting...\n'
api_request "GET" "/orgs/${organisation_id}/projects?limit=1&offset=0&status=active&name=Launch&sort_by=name&sort_direction=asc" "200" "" "${owner_access_token}"
project_count="$(json_get "pagination.count")"
project_total="$(json_get "pagination.total")"
echo "Project list returned ${project_count} item(s) on this page out of ${project_total} matching project(s)."

printf '\n[8/12] Update project...\n'
api_request "PATCH" "/orgs/${organisation_id}/projects/${project_id}" "200" "$(cat <<JSON
{"name":"Launch Checklist Updated ${DEMO_RUN_SLUG}","description":"Updated public-safe smoke demo project","status":"active"}
JSON
)" "${owner_access_token}"
echo "Updated project ${project_id}."

printf '\n[9/12] Create API key for project access...\n'
api_request "POST" "/orgs/${organisation_id}/api-keys" "201" "$(cat <<JSON
{"name":"Local smoke demo automation ${DEMO_RUN_SLUG}"}
JSON
)" "${owner_access_token}" "demo-api-key-${DEMO_RUN_SLUG}"
api_key_id="$(json_get "api_key.id")"
api_key_prefix="$(json_get "api_key.key_prefix")"
raw_api_key="$(json_get "raw_key")"
echo "Created API key ${api_key_id} with prefix ${api_key_prefix}; raw key captured in memory only."

printf '\n[10/12] Use API key on an allowed project endpoint...\n'
api_request "GET" "/orgs/${organisation_id}/projects/${project_id}" "200" "" "${raw_api_key}"
echo "API key project read succeeded for project ${project_id}."

printf '\n[11/12] Revoke API key...\n'
api_request "DELETE" "/orgs/${organisation_id}/api-keys/${api_key_id}" "200" "" "${owner_access_token}"
unset raw_api_key
echo "Revoked API key ${api_key_id}; raw key variable unset."

printf '\n[12/12] Show audit events and check metrics...\n'
api_request "GET" "/orgs/${organisation_id}/audit-events?limit=20&offset=0" "200" "" "${owner_access_token}"
print_audit_summary

api_request "GET" "/metrics" "200"
for metric_name in \
  "saas_api_requests_total" \
  "saas_api_auth_attempts_total" \
  "saas_api_projects_created_total" \
  "saas_api_api_keys_created_total"; do
  if ! grep --quiet "${metric_name}" <<<"${LAST_RESPONSE_BODY}"; then
    echo "Expected metric was not exposed: ${metric_name}" >&2
    exit 1
  fi
done
echo "Metrics endpoint exposed expected API, auth, project, and API key metric families."

cat <<EOF

Smoke demo completed successfully.
Created local demo resources:
- owner user: ${owner_user_id}
- member user: ${member_user_id}
- organisation: ${organisation_id}
- project: ${project_id}
- revoked API key metadata: ${api_key_id} (${api_key_prefix})

The generated data uses example.com emails and local placeholder credentials only.
EOF
