#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../presentation-agent" && pwd)"

echo "=== Running Presentation Builder Script ==="
cd "$PROJECT_ROOT"
npm run demo
