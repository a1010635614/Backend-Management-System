#!/usr/bin/env bash
# Linux Flow runner: Node.js 20+, Python 3.12, Docker Compose for PostgreSQL checks.
set -euo pipefail
: "${COMMIT_SHA:?Map the source commit SHA from Flow}"
[[ "$COMMIT_SHA" =~ ^[a-f0-9]{7,40}$ ]] || exit 2
test "$(git rev-parse HEAD)" = "$COMMIT_SHA" || { echo 'COMMIT_SHA must match the full checked-out commit'; exit 2; }
python3 deploy/test-native-release.py
POSTGRES_TEST_IMAGE=postgres:16-alpine bash deploy/test-postgres.sh
(cd frontend && npm ci && npm run build)
python3 deploy/package_native.py
