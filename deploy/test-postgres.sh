#!/usr/bin/env bash
set -euo pipefail
project="blog-ci-$(date +%s)-$$"
cleanup() { docker compose -p "$project" -f deploy/compose.test.yml down -v --remove-orphans; }
trap cleanup EXIT
docker compose -p "$project" -f deploy/compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
