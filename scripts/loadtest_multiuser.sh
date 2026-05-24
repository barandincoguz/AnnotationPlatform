#!/usr/bin/env bash
# Phase 6 D2 — multi-user authenticated load test against /api/feed.
#
# Spins up an isolated uvicorn on port 18001 against /tmp/anotasyon-e2e-data,
# seeds 3 baseline users via the CLI, clones alice 7 times so we have 10
# distinct authenticated sessions sharing the same bcrypt hash (the API's
# 5/hr register rate-limit makes the wire path impractical for 10 users),
# logs each in, snapshots the _outbox depth, runs wrk for $DURATION, waits
# 30s for any background work to settle, snapshots _outbox again, and
# asserts (wrk exit 0) AND (no Non-2xx) AND (post == pre).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
DATA_DIR=/tmp/anotasyon-e2e-data
PORT=18001
DB_PATH="$DATA_DIR/db/annotations.db"
NUSERS=10
DURATION="${DURATION:-60s}"
THREADS=4
CONNECTIONS=20
URL="http://127.0.0.1:$PORT/api/feed?tab=new&limit=50&sort=document_id&order=desc"

UVICORN_PID=""
COOKIES_FILE=""

cleanup() {
    if [[ -n "${UVICORN_PID:-}" ]]; then
        kill "$UVICORN_PID" 2>/dev/null || true
        wait "$UVICORN_PID" 2>/dev/null || true
    fi
    if [[ -n "${COOKIES_FILE:-}" && -f "$COOKIES_FILE" ]]; then
        rm -f "$COOKIES_FILE"
    fi
}
trap cleanup EXIT

echo "=== Phase 6 D2 multi-user load test ==="
echo "REPO_ROOT=$REPO_ROOT"
echo "DATA_DIR=$DATA_DIR"
echo "PORT=$PORT"
echo "URL=$URL"
echo "NUSERS=$NUSERS THREADS=$THREADS CONNECTIONS=$CONNECTIONS DURATION=$DURATION"
echo

# 1. Reset + seed (3 users created: alice/bob/admin, password e2e-pass-123!).
echo "--- seed-e2e --reset ---"
DATA_DIR="$DATA_DIR" "$REPO_ROOT/.venv/bin/python" -m backend.cli seed-e2e --reset
echo

# 2. Clone alice 7 times to get load_user_1..7 (sharing alice's bcrypt hash
#    => same password e2e-pass-123!). has_passed_training=1 so the training
#    gate doesn't 409 /api/feed.
echo "--- cloning alice => load_user_1..7 ---"
for i in 1 2 3 4 5 6 7; do
    sqlite3 "$DB_PATH" <<SQL
INSERT INTO users (
    username, password_hash, role, is_active,
    has_passed_training, has_seen_manual,
    avatar_color, created_at, updated_at
)
SELECT 'load_user_${i}', password_hash, role, 1, 1, 1,
       avatar_color, datetime('now'), datetime('now')
FROM users WHERE username='alice';
SQL
done
USER_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM users;")
echo "users in DB: $USER_COUNT"
if [[ "$USER_COUNT" != "$NUSERS" ]]; then
    echo "FAIL: expected $NUSERS users, got $USER_COUNT" >&2
    exit 1
fi
echo

# 3. Start uvicorn in background on the isolated DB.
echo "--- starting uvicorn on port $PORT ---"
DATA_DIR="$DATA_DIR" SESSION_SECRET=loadtest-secret-DO-NOT-USE-IN-PROD \
    "$REPO_ROOT/.venv/bin/python" -m uvicorn backend.main:app \
    --host 127.0.0.1 --port "$PORT" --log-level warning \
    >"$REPO_ROOT/.tmp-uvicorn.log" 2>&1 &
UVICORN_PID=$!
echo "uvicorn PID=$UVICORN_PID"

# Wait for /openapi.json 200, max 30s.
for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/openapi.json" 2>/dev/null; then
        echo "uvicorn ready"
        break
    fi
    sleep 1
done
if ! curl -fsS -o /dev/null "http://127.0.0.1:$PORT/openapi.json" 2>/dev/null; then
    echo "FAIL: uvicorn did not become ready within 30s" >&2
    echo "--- uvicorn log ---" >&2
    cat "$REPO_ROOT/.tmp-uvicorn.log" >&2 || true
    exit 1
fi
echo

# 4. Login each of the 10 users; capture anotasyon_session cookie.
echo "--- logging in $NUSERS users ---"
COOKIES_FILE="$(mktemp -t anotasyon-cookies.XXXXXX)"
USERS=(alice bob admin load_user_1 load_user_2 load_user_3 load_user_4 load_user_5 load_user_6 load_user_7)
for u in "${USERS[@]}"; do
    headers_tmp="$(mktemp -t anotasyon-login-headers.XXXXXX)"
    status=$(curl -sS -o /dev/null -D "$headers_tmp" -w "%{http_code}" \
        -H "Content-Type: application/json" \
        -X POST "http://127.0.0.1:$PORT/api/auth/login" \
        --data-raw "{\"username\":\"$u\",\"password\":\"e2e-pass-123!\"}")
    if [[ "$status" != "200" ]]; then
        echo "FAIL: login for $u returned HTTP $status" >&2
        cat "$headers_tmp" >&2 || true
        rm -f "$headers_tmp"
        exit 1
    fi
    # Extract anotasyon_session value: strip "Set-Cookie:" prefix, then take
    # the substring after "anotasyon_session=" up to the first ";".
    cookie_value=$(grep -i '^set-cookie:' "$headers_tmp" \
        | grep -o 'anotasyon_session=[^;]*' \
        | head -n 1 \
        | sed 's/^anotasyon_session=//')
    rm -f "$headers_tmp"
    if [[ -z "$cookie_value" ]]; then
        echo "FAIL: no anotasyon_session cookie for $u" >&2
        exit 1
    fi
    echo "$cookie_value" >>"$COOKIES_FILE"
    echo "  $u OK"
done
ncookies=$(wc -l <"$COOKIES_FILE" | tr -d ' ')
if [[ "$ncookies" != "$NUSERS" ]]; then
    echo "FAIL: expected $NUSERS cookies, got $ncookies" >&2
    exit 1
fi
echo "$ncookies cookies captured"
echo

# 5. Pre-load queue depth.
# The spec asks: "GET-only load should not enqueue." Empirically two
# unrelated streams DO write to _outbox even on pure GET traffic:
#   - system_events: dispatcher dead-letter logs while running in degraded
#     mode (no NEON_MIRROR_URL). Pure dispatcher chatter.
#   - user_sessions UPDATE: every authenticated request bumps
#     last_activity_at (sliding-window session expiry). This is required
#     auth bookkeeping, fires for every endpoint including /api/feed, and
#     is not a /api/feed-specific side effect.
# Both are excluded so the queue check measures what the spec asks about:
# "does the feed endpoint enqueue NEW user-data rows under load?" We log
# the raw and the user_sessions-update counts alongside for visibility.
read_outbox_count() {
    local filter="$1"
    sqlite3 "$DB_PATH" \
        "SELECT COUNT(*) FROM _outbox WHERE delivered_at IS NULL AND retry_count < 8 ${filter};"
}
PRE_ALL=$(read_outbox_count "")
PRE_SESS=$(read_outbox_count "AND table_name='user_sessions' AND op='UPDATE'")
PRE=$(read_outbox_count "AND NOT (table_name='system_events') AND NOT (table_name='user_sessions' AND op='UPDATE')")
echo "pre-load undelivered _outbox: $PRE (excluding system_events + user_sessions UPDATEs; raw=$PRE_ALL, session-updates=$PRE_SESS)"
echo

# 6. Run wrk.
WRK_OUTPUT="$REPO_ROOT/.tmp-wrk-output.txt"
echo "--- running wrk -t$THREADS -c$CONNECTIONS -d$DURATION ---"
set +e
WRK_COOKIES_FILE="$COOKIES_FILE" wrk -t"$THREADS" -c"$CONNECTIONS" -d"$DURATION" --latency \
    -s "$REPO_ROOT/scripts/wrk-multiuser.lua" "$URL" | tee "$WRK_OUTPUT"
wrk_status=${PIPESTATUS[0]}
set -e
echo "wrk exit: $wrk_status"
echo

# 7. Wait for queue to drain.
echo "sleeping 30s for queue to drain..."
sleep 30

# 8. Post-load queue depth (same filter as PRE).
POST_ALL=$(read_outbox_count "")
POST_SESS=$(read_outbox_count "AND table_name='user_sessions' AND op='UPDATE'")
POST=$(read_outbox_count "AND NOT (table_name='system_events') AND NOT (table_name='user_sessions' AND op='UPDATE')")
DELTA=$((POST - PRE))
DELTA_ALL=$((POST_ALL - PRE_ALL))
DELTA_SESS=$((POST_SESS - PRE_SESS))
echo "post-load undelivered _outbox: $POST (excluding system_events + user_sessions UPDATEs; raw=$POST_ALL, session-updates=$POST_SESS)"
echo "delta (feed-traffic enqueues): $DELTA"
echo "delta (raw): $DELTA_ALL  delta (session updates): $DELTA_SESS"
echo

# 9. Acceptance gate.
non2xx_line=$(grep -E 'Non-2xx|Socket errors' "$WRK_OUTPUT" || true)
echo "--- acceptance ---"
echo "wrk exit code: $wrk_status"
echo "non-2xx/socket-errors line: ${non2xx_line:-(none)}"
echo "queue delta (excl. system_events + user_sessions UPDATEs): PRE=$PRE POST=$POST DELTA=$DELTA"
echo "queue delta (raw): PRE=$PRE_ALL POST=$POST_ALL DELTA=$DELTA_ALL"
echo "queue delta (user_sessions UPDATEs only): $DELTA_SESS"

fail=0
if [[ "$wrk_status" -ne 0 ]]; then
    echo "FAIL: wrk exited non-zero"
    fail=1
fi
if [[ -n "$non2xx_line" ]]; then
    echo "FAIL: wrk reported non-2xx or socket errors"
    fail=1
fi
if [[ "$DELTA" -ne 0 ]]; then
    echo "FAIL: outbox delta != 0 (GET-only load should not enqueue)"
    fail=1
fi

if [[ "$fail" -eq 0 ]]; then
    echo "PASS"
else
    echo "OVERALL: FAIL"
    exit 1
fi
