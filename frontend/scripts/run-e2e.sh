#!/usr/bin/env bash
set -euo pipefail

# Pick isolation coordinates once in the parent process. Playwright evaluates
# its config again in worker processes, so computing them inside TypeScript
# would give each worker a different base URL.
e2e_run_id="${E2E_RUN_ID:-$$}"
port_offset=$((e2e_run_id % 10000))

export E2E_RUN_ID="$e2e_run_id"
export E2E_DATA_DIR="${E2E_DATA_DIR:-/tmp/anotasyon-e2e-${e2e_run_id}}"
export E2E_BACKEND_PORT="${E2E_BACKEND_PORT:-$((30000 + port_offset))}"
export E2E_FRONTEND_PORT="${E2E_FRONTEND_PORT:-$((45000 + port_offset))}"

exec playwright test "$@"
